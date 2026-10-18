/**
 * English strings. Voice: plain, direct, second person, sentence case, no
 * exclamation marks (docs/practices/design-system.md § Voice and copy).
 * Portuguese (`pt.ts`) follows the same keys.
 */
export const en = {
  "common.close": "Close",
  "common.required": "(required)",
  "common.loading": "Loading…",
  "common.working": "Working…",

  "nav.label": "Main",
  "nav.skip": "Skip to content",
  "nav.open_menu": "Open menu",
  "nav.close_menu": "Close menu",
  "nav.sign_out": "Sign out",
  "nav.source": "Source code (AGPL-3.0)",
  "nav.home": "Home",
  "nav.health": "Health",
  "nav.social": "Social",
  "nav.email": "Email",
  "nav.analytics": "Analytics",
  "nav.money": "Money",
  "nav.board": "Board",
  "nav.integrations": "Integrations",
  "nav.settings": "Settings",

  "auth.tagline": "Your product's health, audience and money in one place.",
  "auth.sign_in_title": "Sign in",
  "auth.sign_up_title": "Create your account",
  "auth.sign_in": "Sign in",
  "auth.create_account": "Create account",
  "auth.no_account": "New to Commandr?",
  "auth.have_account": "Already have an account?",
  "auth.email": "Email",
  "auth.password": "Password",
  "auth.password_help": "At least 12 characters. A short sentence works well.",
  "auth.verify_email": "Check your inbox: we sent you a link to confirm your email address.",
  "auth.mfa_pending":
    "This account uses two-step verification, which this screen does not support yet.",
  "auth.generic_error": "That did not work. Check your details and try again.",
  "auth.network_error": "We could not reach Commandr. Check your connection and try again.",

  "onboarding.title": "Set up your workspace",
  "onboarding.org_name": "Organization name",
  "onboarding.org_help": "Your company, or your own name if you work alone.",
  "onboarding.country": "Country",
  "onboarding.country_help": "Two letters, like PT.",
  "onboarding.currency": "Currency",
  "onboarding.project_name": "Product name",
  "onboarding.project_url": "Product website",
  "onboarding.project_kind": "What are you building?",
  "onboarding.project_kind_help": "This decides which integrations we suggest first.",
  "onboarding.submit": "Continue to integrations",

  "kind.web_app": "Web app",
  "kind.mobile_app": "Mobile app",
  "kind.api": "API",
  "kind.shop": "Shop",

  "catalogue.title": "Integrations",
  "catalogue.subtitle": "Connect what you already use. Each one unlocks part of Commandr.",
  "catalogue.search_label": "Search integrations",
  "catalogue.search_placeholder": "Search integrations",
  "catalogue.load_error": "We could not load the integrations. Reload the page to try again.",
  "catalogue.recommended": "Recommended first",
  "catalogue.recommended_progress": "{done} of {total} connected",
  "catalogue.all": "All integrations",
  "catalogue.filter_label": "Filter by category",
  "catalogue.filter_all": "All",
  "catalogue.results": "{n} integrations shown",
  "catalogue.no_results": "No integrations match your search.",
  "catalogue.connect": "Connect",
  "catalogue.fix": "Fix",
  "catalogue.manage": "Manage",
  "catalogue.requirements_label": "What {name} needs",
  "catalogue.setup_seconds": "~{n} s",
  "catalogue.setup_minutes": "~{n} min",
  "catalogue.state.setting_up": "Setting up",
  "catalogue.state.connected": "Connected",
  "catalogue.state.needs_attention": "Needs attention",

  "setup.title": "Connect {name}",
  "setup.steps_heading": "What you will do",
  "setup.needs_heading": "What you need",
  "setup.no_steps_yet": "Setup steps for this integration are being written.",
  "setup.phase_badge": "Coming in phase {phase}",
  "setup.coming_soon":
    "Connecting this integration arrives in phase {phase}. The steps above are what it will ask of you.",
  "setup.start": "Start setup",

  "placeholder.go_to_integrations": "Go to integrations",
  "placeholder.home":
    "Your dashboard builds itself from what you connect. Start with an integration.",
  "placeholder.health":
    "Connect the uptime probe, a heartbeat or the Django SDK to see your app's health here.",
  "placeholder.social": "Connect Instagram, Facebook or TikTok to plan and publish posts here.",
  "placeholder.email": "Connect Resend to schedule newsletters and announcements here.",
  "placeholder.analytics":
    "Connect Google Analytics to see traffic next to your app's own numbers.",
  "placeholder.money":
    "Turn on the ledger, or connect Stripe and your ad accounts, to see your numbers here.",
  "placeholder.board":
    "The board arrives in phase 1, with cards you can create from alerts and posts.",
  "placeholder.settings": "Organization, members and billing settings arrive in phase 1.",
} as const;
