"""MongoDB collections for Dentist Portal — reuses existing Motor client."""

from orchestrator.database import Database


def get_portal_db():
    return Database.get_db()


def get_portal_users_col():
    return get_portal_db()["portal_users"]


def get_portal_products_col():
    return get_portal_db()["portal_products"]


def get_portal_sessions_col():
    return get_portal_db()["portal_sessions"]


def get_portal_recommendations_col():
    return get_portal_db()["portal_recommendations"]


def get_portal_orders_col():
    return get_portal_db()["portal_orders"]


def get_portal_dentist_recommendations_col():
    return get_portal_db()["portal_dentist_recommendations"]


def get_portal_appointments_col():
    return get_portal_db()["portal_appointments"]


async def init_portal_indexes():
    """Create indexes for all portal collections."""
    users = get_portal_users_col()
    products = get_portal_products_col()
    sessions = get_portal_sessions_col()
    recs = get_portal_recommendations_col()
    orders = get_portal_orders_col()
    dentist_recs = get_portal_dentist_recommendations_col()
    appointments = get_portal_appointments_col()

    await users.create_index("email", unique=True)
    await users.create_index("role")
    try:
        await users.create_index([("coordinates", "2dsphere")])
    except Exception:
        pass

    await products.create_index("dentist_id")
    await products.create_index("category")
    await products.create_index("status")
    await products.create_index([("name", "text"), ("ai_description", "text")])

    await sessions.create_index("session_id", unique=True)
    await sessions.create_index("patient_id")

    await recs.create_index("session_id")
    await recs.create_index("patient_id")

    await orders.create_index("dentist_id")
    await orders.create_index("created_at")

    await dentist_recs.create_index("session_id")
    await dentist_recs.create_index("patient_id")

    await appointments.create_index("dentist_id")
    await appointments.create_index("patient_id")
    await appointments.create_index("status")

    print("[PORTAL] MongoDB indexes initialized")
