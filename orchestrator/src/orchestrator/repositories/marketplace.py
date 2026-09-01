"""Dentist, commerce, recommendation, and appointment repositories."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.db.models import (
    AppointmentRequest,
    Dentist,
    DentistRecommendation,
    Order,
    Product,
    ProductRecommendation,
    User,
)


class DentistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, dentist: Dentist) -> Dentist:
        self.session.add(dentist)
        await self.session.flush()
        return dentist

    async def get(self, dentist_id: UUID) -> Dentist | None:
        return await self.session.get(Dentist, dentist_id)

    async def get_by_owner(self, owner_user_id: UUID) -> Dentist | None:
        result = await self.session.execute(
            select(Dentist).where(Dentist.owner_user_id == owner_user_id)
        )
        return result.scalar_one_or_none()

    async def list_platform(self, limit: int = 200) -> list[tuple[Dentist, User | None]]:
        result = await self.session.execute(
            select(Dentist, User)
            .outerjoin(User, User.id == Dentist.owner_user_id)
            .where(Dentist.source == "platform", Dentist.is_active.is_(True))
            .limit(limit)
        )
        return list(result.all())


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, product: Product) -> Product:
        self.session.add(product)
        await self.session.flush()
        return product

    async def get(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_owned(self, product_id: UUID, owner_user_id: UUID) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .join(Dentist, Dentist.id == Product.dentist_id)
            .where(Product.id == product_id, Dentist.owner_user_id == owner_user_id)
        )
        return result.scalar_one_or_none()

    async def list_active(
        self, *, category: str | None = None, search: str | None = None, limit: int = 50
    ) -> list[Product]:
        query = select(Product).where(Product.status == "active")
        if category:
            query = query.where(Product.category == category)
        if search:
            term = f"%{search}%"
            query = query.where(
                or_(Product.name.ilike(term), Product.ai_description.ilike(term))
            )
        result = await self.session.execute(
            query.order_by(Product.created_at.desc()).limit(limit)
        )
        return list(result.scalars())

    async def list_owned(self, owner_user_id: UUID) -> list[Product]:
        result = await self.session.execute(
            select(Product)
            .join(Dentist, Dentist.id == Product.dentist_id)
            .where(Dentist.owner_user_id == owner_user_id)
            .order_by(Product.created_at.desc())
        )
        return list(result.scalars())

    async def delete(self, product: Product) -> None:
        await self.session.delete(product)
        await self.session.flush()


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, order: Order) -> Order:
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_owned_by_dentist(
        self, order_id: UUID, owner_user_id: UUID
    ) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .join(Dentist, Dentist.id == Order.dentist_id)
            .where(Order.id == order_id, Dentist.owner_user_id == owner_user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_dentist(self, owner_user_id: UUID, limit: int = 100) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .join(Dentist, Dentist.id == Order.dentist_id)
            .where(Dentist.owner_user_id == owner_user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())


class RecommendationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_product(self, recommendation: ProductRecommendation) -> ProductRecommendation:
        self.session.add(recommendation)
        await self.session.flush()
        return recommendation

    async def list_product_for_patient(
        self, patient_user_id: UUID, limit: int = 20
    ) -> list[ProductRecommendation]:
        result = await self.session.execute(
            select(ProductRecommendation)
            .where(ProductRecommendation.patient_user_id == patient_user_id)
            .order_by(ProductRecommendation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def add_dentist(self, recommendation: DentistRecommendation) -> DentistRecommendation:
        self.session.add(recommendation)
        await self.session.flush()
        return recommendation


class AppointmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, appointment: AppointmentRequest) -> AppointmentRequest:
        self.session.add(appointment)
        await self.session.flush()
        return appointment

    async def get_for_principal(
        self, appointment_id: UUID, *, user_id: UUID, role: str
    ) -> AppointmentRequest | None:
        query = select(AppointmentRequest).where(AppointmentRequest.id == appointment_id)
        if role == "patient":
            query = query.where(AppointmentRequest.patient_user_id == user_id)
        elif role == "dentist":
            query = query.join(Dentist, Dentist.id == AppointmentRequest.dentist_id).where(
                Dentist.owner_user_id == user_id
            )
        elif role != "admin":
            return None
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_for_principal(
        self, *, user_id: UUID, role: str, limit: int = 100
    ) -> list[AppointmentRequest]:
        query = select(AppointmentRequest)
        if role == "patient":
            query = query.where(AppointmentRequest.patient_user_id == user_id)
        elif role == "dentist":
            query = query.join(Dentist, Dentist.id == AppointmentRequest.dentist_id).where(
                Dentist.owner_user_id == user_id
            )
        elif role != "admin":
            return []
        result = await self.session.execute(
            query.order_by(AppointmentRequest.created_at.desc()).limit(limit)
        )
        return list(result.scalars())
