"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import styles from "./landing.module.css";

/* ─── Data ─── */
const NAV_ITEMS = [
  { href: "#home", label: "Home" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#features", label: "Features" },
  { href: "#why", label: "About" },
  { href: "#team", label: "FAQ" },
];

const FEATURES_TOP = [
  {
    num: 1,
    title: "AI DENTAL SCANNER",
    desc: "Upload a photo and receive instant insights.",
    col: 1,
  },
  {
    num: 3,
    title: "NEARBY DENTISTS",
    desc: "Get recommendations based on your location.",
    col: 3,
  },
  {
    num: 5,
    title: "PERSONALIZED TIPS",
    desc: "Receive recommendations tailored to your habits.",
    col: 5,
  },
];

const FEATURES_BOTTOM = [
  {
    num: 2,
    title: "SMART DENTAL ASSISTANT",
    desc: "Ask questions about oral health anytime.",
    col: 2,
  },
  {
    num: 4,
    title: "SMART REMINDERS",
    desc: "Never forget brushing, flossing, or checkups.",
    col: 4,
  },
];

const BENEFITS = [
  {
    heading: "DETECT EARLIER",
    colorClass: "blue" as const,
    desc: "Identify Visible Signs Before They Become Severe.",
    mascotLeft: true,
  },
  {
    heading: "SAVE MONEY",
    colorClass: "navy" as const,
    desc: "Early Detection Costs Less Than Major Treatments.",
    mascotLeft: false,
  },
  {
    heading: "BETTER HABITS",
    colorClass: "blue" as const,
    desc: "Build Daily Routines That Protect Your Smile.",
    mascotLeft: true,
  },
  {
    heading: "FIND DENTISTS\nFASTER",
    colorClass: "navy" as const,
    desc: "Trusted Recommendations When You Need Help.",
    mascotLeft: false,
  },
];

const TEAM = [
  { name: "Nathan", img: "/landing/team-nathan.png" },
  { name: "Anas", img: "/landing/team-anas.png" },
  { name: "Laraib", img: "/landing/team-laraib.png" },
  { name: "Hasnain", img: "/landing/team-hasnain.png" },
];

/* ─── Component ─── */
export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);

  /* Scroll-reveal via IntersectionObserver */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add(styles.visible);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
    );
    const els = document.querySelectorAll(`.${styles.animateIn}`);
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div className={styles.page}>

      {/* ═══════════════════════════════ NAVBAR ═══════════════════════════════ */}
      <header className={styles.nav} id="home">
        <div className={styles.navInner}>
          <Link href="/" className={styles.logoLink} aria-label="DaantShant home">
            <Image
              src="/landing/logo.png"
              alt="DaantShant"
              width={167}
              height={78}
              className={styles.logoImg}
              priority
            />
          </Link>

          <nav
            className={`${styles.navLinks} ${menuOpen ? styles.navOpen : ""}`}
            aria-label="Main navigation"
          >
            {NAV_ITEMS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className={styles.navLink}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </a>
            ))}
          </nav>

          <Link href="/get-started" className={styles.navCta}>
            Get Started
          </Link>

          <button
            type="button"
            className={styles.menuBtn}
            aria-label="Toggle navigation menu"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </header>

      {/* ═══════════════════════════════ HERO ═══════════════════════════════ */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>

          {/* Left text column */}
          <div className={styles.heroLeft}>
            <h1 className={`${styles.heroScan} ${styles.animateIn}`}>SCAN</h1>
            <p
              className={`${styles.heroDetect} ${styles.animateIn}`}
              style={{ transitionDelay: "0.1s" }}
            >
              DETECT.
            </p>
            <div
              className={`${styles.heroCopyBottom} ${styles.animateIn}`}
              style={{ transitionDelay: "0.2s" }}
            >
              <p className={styles.heroStat}>
                95% OF PEOPLE IGNORE DENTAL
                <br />
                ISSUES UNTIL IT&apos;S TOO LATE.
              </p>
              <Link href="/get-started" className={styles.heroCta}>
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M12 2C9.24 2 7 4.24 7 7C7 8.72 7.88 10.23 9.2 11.1C7.28 11.88 6 13.8 6 16C6 16.55 6.45 17 7 17H17C17.55 17 18 16.55 18 16C18 13.8 16.72 11.88 14.8 11.1C16.12 10.23 17 8.72 17 7C17 4.24 14.76 2 12 2Z"
                    fill="currentColor"
                  />
                  <path
                    d="M9 17V20C9 21.1 9.9 22 11 22H13C14.1 22 15 21.1 15 20V17H9Z"
                    fill="currentColor"
                  />
                </svg>
                SCAN MY TEETH
              </Link>
            </div>
          </div>

          {/* Center: dental scanner (3D float) */}
          <div className={styles.heroScannerWrap} aria-hidden="true">
            <Image
              src="/landing/hero-scanner.png"
              alt="AI dental scanning tool"
              fill
              style={{ objectFit: "contain", objectPosition: "top center" }}
              priority
            />
          </div>

          {/* Right: teeth models + PROTECT */}
          <div className={styles.heroRight}>
            <div className={styles.heroTeethWhiteWrap}>
              <Image
                src="/landing/hero-teeth-white.png"
                alt="White dental model"
                fill
                style={{ objectFit: "contain" }}
                priority
              />
            </div>
            <p className={styles.heroProtect}>PROTECT.</p>
            <div className={styles.heroTeethRedWrap}>
              <Image
                src="/landing/hero-teeth-red.png"
                alt="Dental anatomy illustration"
                fill
                style={{ objectFit: "contain" }}
              />
            </div>
          </div>

        </div>
      </section>

      {/* ═══════════════════════════════ FEATURES ═══════════════════════════════ */}
      <section id="features" className={styles.features}>
        <div className={styles.featuresInner}>
          <h2 className={`${styles.featuresTitle} ${styles.animateIn}`}>
            FEATURES SECTION
          </h2>
          <p className={`${styles.featuresSub} ${styles.animateIn}`} style={{ transitionDelay: "0.1s" }}>
            EVERYTHING YOU NEED FOR BETTER ORAL HEALTH
          </p>

          {/* Diamond grid */}
          <div className={styles.featureDiamondGrid}>
            {/* Top row: cols 1, 3, 5 */}
            <div className={styles.featureTopRow}>
              {FEATURES_TOP.map((f, i) => (
                <div
                  key={f.num}
                  className={`${styles.featureItem} ${styles.animateIn}`}
                  style={{ gridColumn: f.col, transitionDelay: `${i * 0.1}s` }}
                >
                  <h3 className={styles.featureItemTitle}>{f.title}</h3>
                  <p className={styles.featureItemDesc}>{f.desc}</p>
                </div>
              ))}
            </div>

            {/* SVG zigzag */}
            <svg
              className={styles.featureSvg}
              viewBox="0 0 1200 200"
              preserveAspectRatio="xMidYMid meet"
              aria-hidden="true"
            >
              <defs>
                <filter id="diamondGlow">
                  <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                  <feMerge>
                    <feMergeNode in="coloredBlur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              {/* Connecting zigzag line */}
              <path
                d="M100,38 L350,162 L600,38 L850,162 L1100,38"
                stroke="#00a2f0"
                strokeWidth="2.5"
                fill="none"
                opacity="0.75"
              />
              {/* 5 diamonds */}
              {[
                { x: 100, y: 38, n: 1 },
                { x: 350, y: 162, n: 2 },
                { x: 600, y: 38, n: 3 },
                { x: 850, y: 162, n: 4 },
                { x: 1100, y: 38, n: 5 },
              ].map((d) => (
                <g
                  key={d.n}
                  transform={`translate(${d.x},${d.y})`}
                  filter="url(#diamondGlow)"
                >
                  <rect
                    x="-30"
                    y="-30"
                    width="60"
                    height="60"
                    transform="rotate(45)"
                    fill="rgba(255,255,255,0.18)"
                    stroke="rgba(255,255,255,0.75)"
                    strokeWidth="2"
                    rx="6"
                  />
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="white"
                    fontSize="22"
                    fontFamily="Arial, sans-serif"
                    fontWeight="bold"
                  >
                    {d.n}
                  </text>
                </g>
              ))}
            </svg>

            {/* Bottom row: cols 2, 4 */}
            <div className={styles.featureBottomRow}>
              {FEATURES_BOTTOM.map((f, i) => (
                <div
                  key={f.num}
                  className={`${styles.featureItem} ${styles.animateIn}`}
                  style={{ gridColumn: f.col, transitionDelay: `${i * 0.1 + 0.3}s` }}
                >
                  <h3 className={styles.featureItemTitle}>{f.title}</h3>
                  <p className={styles.featureItemDesc}>{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════ BRAND LOGO ═══════════════════════════════ */}
      <section className={`${styles.brandSection} ${styles.animateIn}`}>
        <div className={styles.brandLogoWrap}>
          <Image
            src="/landing/logo-full.png"
            alt="DaantShant — AI dental health"
            width={543}
            height={253}
            className={styles.brandLogoImg}
          />
        </div>
      </section>

      {/* ═══════════════════════════════ WHY — text only ═══════════════════════════════ */}
      <section id="why" className={styles.whySection}>
        <div className={styles.whyWatermark} aria-hidden="true">sh</div>
        <div className={`${styles.whyContent} ${styles.animateIn}`}>
          <h2 className={styles.whyTitle}>WHY DAANTSHANT?</h2>
          <p className={styles.whyText}>
            Identify{" "}
            <span className={styles.accentOrange}>Visible Signs</span>{" "}
            Before They Become Severe.
          </p>
          <p className={styles.whyText}>
            Build Daily Routines That Protect Your{" "}
            <span className={styles.accentBlue}>Smile.</span>
          </p>
          <p className={styles.whyText}>
            Trusted{" "}
            <span className={styles.accentGreen}>Recommendations</span>{" "}
            When You Need Help.
          </p>
        </div>
      </section>

      {/* ═══════════════════════════════ WHY — with mascot ═══════════════════════════════ */}
      <section className={styles.whyMascotSection}>
        <div className={styles.whyMascotWrap}>
          <div className={styles.whyMascotImgCol}>
            <Image
              src="/landing/mascot.png"
              alt="DaantShant robot mascot"
              width={301}
              height={416}
              className={styles.mascotFloat}
            />
          </div>
          <div className={`${styles.whyMascotText} ${styles.animateIn}`}>
            <div className={styles.whyWatermarkSmall} aria-hidden="true">sh</div>
            <h2 className={styles.whyTitle}>WHY DAANTSHANT?</h2>
            <p className={styles.whyText}>
              Identify{" "}
              <span className={styles.accentOrange}>Visible Signs</span>{" "}
              Before They Become Severe.
            </p>
            <p className={styles.whyText}>
              Build Daily Routines That Protect Your{" "}
              <span className={styles.accentBlue}>Smile.</span>
            </p>
            <p className={styles.whyText}>
              Trusted{" "}
              <span className={styles.accentGreen}>Recommendations</span>{" "}
              When You Need Help.
            </p>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════ BENEFITS ═══════════════════════════════ */}
      <section className={styles.benefits} id="how-it-works">
        {BENEFITS.map((b, i) => (
          <div
            key={b.heading}
            className={`${styles.benefitRow} ${b.mascotLeft ? "" : styles.benefitRowReverse} ${styles.animateIn}`}
            style={{ transitionDelay: `${i * 0.08}s` }}
          >
            <div className={styles.benefitMascot}>
              <Image
                src="/landing/mascot.png"
                alt={b.heading.replace("\n", " ")}
                width={557}
                height={416}
                className={styles.mascotFloat}
              />
            </div>
            <div className={styles.benefitText}>
              <h3
                className={`${styles.benefitTitle} ${
                  b.colorClass === "blue" ? styles.titleBlue : styles.titleNavy
                }`}
              >
                {b.heading.split("\n").map((line, li) => (
                  <span key={li}>
                    {line}
                    {li < b.heading.split("\n").length - 1 && <br />}
                  </span>
                ))}
              </h3>
              <p className={styles.benefitDesc}>{b.desc}</p>
            </div>
          </div>
        ))}
      </section>

      {/* ═══════════════════════════════ SMILE / TEAM ═══════════════════════════════ */}
      <section id="team" className={styles.teamSection}>
        <div className={styles.teamInner}>
          <h2 className={`${styles.teamTitle} ${styles.animateIn}`}>
            SMILE WITH CONFIDENCE
          </h2>
          <p
            className={`${styles.teamSub} ${styles.animateIn}`}
            style={{ transitionDelay: "0.1s" }}
          >
            Healthy Teeth. Better Confidence.
          </p>
          <div className={styles.teamGrid}>
            {TEAM.map((member, i) => (
              <div
                key={member.name}
                className={`${styles.teamMember} ${styles.animateIn}`}
                style={{ transitionDelay: `${i * 0.1}s` }}
              >
                <Image
                  src={member.img}
                  alt={`Team member ${member.name}`}
                  width={467}
                  height={625}
                  className={styles.teamPhoto}
                />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════ FOOTER ═══════════════════════════════ */}
      <footer className={styles.footer}>
        {/* Large brand watermark */}
        <div className={styles.footerBrandWatermark} aria-hidden="true">
          <div className={styles.footerLogoWrap}>
            <Image
              src="/landing/logo-full.png"
              alt=""
              fill
              style={{ objectFit: "contain" }}
            />
          </div>
        </div>

        {/* Footer body */}
        <div className={styles.footerBody}>
          {/* Gradient divider line */}
          <div className={styles.footerDivider} />

          <div className={styles.footerGrid}>
            {/* Social icons */}
            <div className={styles.footerSocials}>
              <a href="#" aria-label="Facebook" className={styles.socialLink}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
                </svg>
              </a>
              <a href="#" aria-label="X / Twitter" className={styles.socialLink}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </a>
              <a href="#" aria-label="YouTube" className={styles.socialLink}>
                <svg width="22" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46a2.78 2.78 0 0 0-1.95 1.96A29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58A2.78 2.78 0 0 0 3.41 19.6C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.95A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58zM9.75 15.02V8.98L15.5 12l-5.75 3.02z" />
                </svg>
              </a>
              <a href="#" aria-label="WhatsApp" className={styles.socialLink}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a6.34 6.34 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.890-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z" />
                </svg>
              </a>
            </div>

            {/* Company Info */}
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Company Info</h4>
              <div className={styles.footerContact}>
                <svg width="16" height="20" viewBox="0 0 16 20" fill="none" aria-hidden="true">
                  <path d="M8 1C5.24 1 3 3.24 3 6C3 9.75 8 15 8 15C8 15 13 9.75 13 6C13 3.24 10.76 1 8 1Z" stroke="#00a2f0" strokeWidth="1.5" fill="none"/>
                  <circle cx="8" cy="6" r="2" fill="#00a2f0"/>
                </svg>
                <span>+92 333 7777475</span>
              </div>
              <div className={styles.footerContact}>
                <svg width="16" height="20" viewBox="0 0 16 20" fill="none" aria-hidden="true">
                  <path d="M8 1C5.24 1 3 3.24 3 6C3 9.75 8 15 8 15C8 15 13 9.75 13 6C13 3.24 10.76 1 8 1Z" stroke="#00a2f0" strokeWidth="1.5" fill="none"/>
                  <circle cx="8" cy="6" r="2" fill="#00a2f0"/>
                </svg>
                <span>+92 55 4298858</span>
              </div>
              <div className={styles.footerContact}>
                <svg width="20" height="16" viewBox="0 0 20 16" fill="none" aria-hidden="true">
                  <rect x="1" y="1" width="18" height="14" rx="2" stroke="#00a2f0" strokeWidth="1.5"/>
                  <path d="M1 4L10 10L19 4" stroke="#00a2f0" strokeWidth="1.5"/>
                </svg>
                <span>info@burhangas.com</span>
              </div>
              <div className={styles.footerContact}>
                <svg width="20" height="16" viewBox="0 0 20 16" fill="none" aria-hidden="true">
                  <rect x="1" y="1" width="18" height="14" rx="2" stroke="#00a2f0" strokeWidth="1.5"/>
                  <path d="M1 4L10 10L19 4" stroke="#00a2f0" strokeWidth="1.5"/>
                </svg>
                <span>burhancomposites@gmail.com</span>
              </div>
            </div>

            {/* Useful Links */}
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Useful Links</h4>
              {["Home", "Online store", "Case Studies", "Locations"].map((link) => (
                <a key={link} href="#" className={styles.footerLink}>
                  {link}
                </a>
              ))}
            </div>

            {/* Explore More */}
            <div className={styles.footerCol}>
              <h4 className={styles.footerColTitle}>Explore More</h4>
              {["Our Cylinders", "Our Company", "Our Technology"].map((link) => (
                <a key={link} href="#" className={styles.footerLink}>
                  {link}
                </a>
              ))}
              <h4 className={`${styles.footerColTitle} ${styles.footerSubTitle}`}>
                Working Hours
              </h4>
              <p className={styles.footerLink}>Sat - Thu : 9AM - 5AM</p>
            </div>
          </div>

          {/* Bottom bar */}
          <div className={styles.footerBar}>
            <span className={styles.footerCopy}>
              Shop.co © 2000-2023, All Rights Reserved
            </span>
            <div className={styles.footerPayments} aria-label="Accepted payment methods">
              <span className={styles.payVisa}>VISA</span>
              <span className={styles.payMc}>●●</span>
              <span className={styles.payGpay}>G Pay</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
