"use client";

import Link from "next/link";
import Image from "next/image";

interface DaantShaantLogoProps {
  href?: string;
  className?: string;
  width?: number;
  height?: number;
  priority?: boolean;
}

export function DaantShaantLogo({
  href = "/",
  className,
  width = 167,
  height = 78,
  priority = false,
}: DaantShaantLogoProps) {
  const content = (
    <Image
      src="/landing/logo.png"
      alt="DaantShaant"
      width={width}
      height={height}
      priority={priority}
      style={{
        objectFit: "contain",
        width: "auto",
        height: "38px",
        display: "block",
      }}
    />
  );

  if (href) {
    return (
      <Link href={href} className={className} aria-label="DaantShaant">
        {content}
      </Link>
    );
  }

  return <div className={className}>{content}</div>;
}
