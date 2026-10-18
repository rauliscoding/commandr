"""The v1 integration catalogue (docs/product/onboarding-and-catalogue.md).

Phase 0 declares every connector so the catalogue is complete and honest about
what is coming; each one becomes `Availability.AVAILABLE` when its connector
package (auth + sync) lands, via the `/add-connector` skill.
"""

from commandr.integrations.registry import (
    AuthType,
    Capability,
    Category,
    ConnectorMeta,
    Requirement,
    SetupStep,
    recommend,
    register,
)
from commandr.tenancy.models import ProjectKind

C = Capability
R = Requirement

# --- App health --------------------------------------------------------------
register(
    ConnectorMeta(
        slug="uptime_probe",
        name="Uptime probe",
        category=Category.APP_HEALTH,
        auth=AuthType.NONE,
        unlocks="Know within a minute when your site or API is down.",
        setup_minutes=0.5,
        phase=1,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE,),
        logo_text="UP",
        docs_path="connectors/uptime-probe",
        steps=(
            SetupStep("Enter the address to check", "An https:// URL, such as your /healthz/."),
            SetupStep("Choose how often", "Every 1 or 5 minutes, depending on your plan."),
            SetupStep("See the first check", "We run one straight away and show the result."),
        ),
    )
)
register(
    ConnectorMeta(
        slug="heartbeat",
        name="Heartbeat",
        category=Category.APP_HEALTH,
        auth=AuthType.INGEST_KEY,
        unlocks="Get told when a scheduled job stops running.",
        setup_minutes=1,
        phase=1,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE, R.CODE_CHANGE),
        logo_text="HB",
        docs_path="connectors/heartbeat",
        steps=(
            SetupStep("Name the job and its schedule", "For example: nightly backup, every 24 h."),
            SetupStep("Call your heartbeat URL", "Add one curl line at the end of the job."),
            SetupStep("See the first beat", "We show it as soon as it arrives."),
        ),
    )
)
register(
    ConnectorMeta(
        slug="status_endpoint",
        name="Status endpoint",
        category=Category.APP_HEALTH,
        auth=AuthType.HMAC_SECRET,
        unlocks="Health checks, gauges and KPIs pulled from your app every few minutes.",
        setup_minutes=10,
        phase=1,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE, R.CODE_CHANGE),
        logo_text="SE",
        docs_path="connectors/status-endpoint",
        steps=(
            SetupStep("Copy your signing secret", "Your app uses it to check our requests."),
            SetupStep(
                "Expose the status document",
                "Serve /.well-known/commandr/status in the format the contract describes.",
            ),
            SetupStep("Enter its address", "We send a signed test request and show the result."),
        ),
    )
)
register(
    ConnectorMeta(
        slug="push_api",
        name="Push API",
        category=Category.APP_HEALTH,
        auth=AuthType.INGEST_KEY,
        unlocks="Send events, counters and errors from anywhere your code runs.",
        setup_minutes=10,
        phase=1,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE, R.CODE_CHANGE),
        logo_text="API",
        docs_path="connectors/push-api",
        steps=(
            SetupStep("Create an ingest key", "Write-only, shown once. Keep it server-side."),
            SetupStep("Send a test batch", "POST /v1/ingest with the example payload."),
            SetupStep("See it arrive", "Accepted items appear here within a minute."),
        ),
    )
)
register(
    ConnectorMeta(
        slug="django_sdk",
        name="Django SDK",
        category=Category.APP_HEALTH,
        auth=AuthType.INGEST_KEY,
        unlocks="Health checks, errors, per-route traffic and KPIs from one pip install.",
        setup_minutes=5,
        phase=1,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE, R.CODE_CHANGE),
        logo_text="dj",
        docs_path="connectors/django-sdk",
        steps=(
            SetupStep("Install the package", "pip install commandr-django"),
            SetupStep("Add three settings", "Your ingest key, signing secret and service name."),
            SetupStep("Deploy and wait for data", "Checks and traffic appear within a minute."),
        ),
    )
)

# --- Social ------------------------------------------------------------------
_META_APP_STEPS = (
    SetupStep("Create a Meta app", "In Meta for Developers, choose the Business app type."),
    SetupStep("Add the products and permissions", "We list exactly which ones, and why."),
    SetupStep("Paste our redirect URL into your app", "Copy it from here."),
    SetupStep("Keep the app in development mode", "You are its admin, so no review is needed."),
    SetupStep("Paste your App ID and App Secret", "Stored encrypted; never shown again."),
    SetupStep("Connect your accounts", "Sign in with Facebook and pick what to connect."),
)
register(
    ConnectorMeta(
        slug="instagram",
        name="Instagram",
        category=Category.SOCIAL,
        auth=AuthType.OAUTH_BYO_APP,
        unlocks="Schedule posts and see their reach, likes and saves.",
        setup_minutes=15,
        phase=1,
        capabilities=frozenset({C.PUBLISH, C.SCHEDULE, C.READ_CONTENT, C.READ_METRICS}),
        requirements=(R.FREE, R.NEEDS_META_APP, R.BUSINESS_ACCOUNT),
        logo_text="IG",
        docs_path="connectors/instagram",
        steps=_META_APP_STEPS,
    )
)
register(
    ConnectorMeta(
        slug="facebook_page",
        name="Facebook Page",
        category=Category.SOCIAL,
        auth=AuthType.OAUTH_BYO_APP,
        unlocks="Publish to your Page and see how posts perform.",
        setup_minutes=15,
        phase=1,
        capabilities=frozenset({C.PUBLISH, C.SCHEDULE, C.READ_CONTENT, C.READ_METRICS}),
        requirements=(R.FREE, R.NEEDS_META_APP),
        logo_text="FB",
        docs_path="connectors/facebook-page",
        steps=_META_APP_STEPS,
    )
)
register(
    ConnectorMeta(
        slug="tiktok",
        name="TikTok",
        category=Category.SOCIAL,
        auth=AuthType.OAUTH_BYO_APP,
        unlocks="Send videos to your TikTok drafts on schedule and track their views.",
        setup_minutes=15,
        phase=1,
        capabilities=frozenset({C.PUBLISH, C.SCHEDULE, C.READ_METRICS}),
        requirements=(R.FREE, R.NEEDS_TIKTOK_APP),
        logo_text="TT",
        docs_path="connectors/tiktok",
        steps=(
            SetupStep(
                "Create a TikTok developer app", "Add Login Kit and the Content Posting API."
            ),
            SetupStep("Paste our redirect URL into your app", "Copy it from here."),
            SetupStep("Paste your client key and secret", "Stored encrypted; never shown again."),
            SetupStep("Connect your account", "Until TikTok audits your app, posts go to drafts."),
        ),
    )
)

# --- Email -------------------------------------------------------------------
register(
    ConnectorMeta(
        slug="resend",
        name="Resend",
        category=Category.EMAIL,
        auth=AuthType.API_KEY,
        unlocks="Schedule newsletters and announcements, and see who opened them.",
        setup_minutes=2,
        phase=1,
        capabilities=frozenset({C.READ_CONTENT, C.SCHEDULE, C.READ_METRICS, C.WEBHOOK}),
        requirements=(R.API_KEY,),
        logo_text="Rs",
        docs_path="connectors/resend",
        steps=(
            SetupStep("Create an API key in Resend", "Full access is needed to send broadcasts."),
            SetupStep("Paste it here", "Stored encrypted; never shown again."),
            SetupStep("See your audiences", "We list them so you can pick one."),
        ),
    )
)

# --- Analytics & ads ---------------------------------------------------------
register(
    ConnectorMeta(
        slug="ga4",
        name="Google Analytics",
        category=Category.ANALYTICS,
        auth=AuthType.OAUTH_PLATFORM,
        unlocks="Traffic, sources and conversions next to your app's own numbers.",
        setup_minutes=3,
        phase=2,
        capabilities=frozenset({C.READ_METRICS}),
        requirements=(R.FREE,),
        logo_text="GA",
        docs_path="connectors/ga4",
        steps=(
            SetupStep("Sign in with Google", "Read-only access to Analytics."),
            SetupStep("Pick a property", "The one that tracks this project."),
            SetupStep("See the last 30 days", "Loaded straight away."),
        ),
    )
)
register(
    ConnectorMeta(
        slug="google_ads",
        name="Google Ads",
        category=Category.ADS,
        auth=AuthType.OAUTH_PLATFORM,
        unlocks="Spend, clicks and cost per conversion, added to your ledger.",
        setup_minutes=3,
        phase=2,
        capabilities=frozenset({C.READ_SPEND, C.READ_METRICS}),
        requirements=(R.FREE,),
        logo_text="GAd",
        docs_path="connectors/google-ads",
    )
)
register(
    ConnectorMeta(
        slug="meta_ads",
        name="Meta Ads",
        category=Category.ADS,
        auth=AuthType.OAUTH_BYO_APP,
        unlocks="Facebook and Instagram ad spend and results, added to your ledger.",
        setup_minutes=10,
        phase=2,
        capabilities=frozenset({C.READ_SPEND, C.READ_METRICS}),
        requirements=(R.FREE, R.NEEDS_META_APP),
        logo_text="MA",
        docs_path="connectors/meta-ads",
    )
)

# --- Money -------------------------------------------------------------------
register(
    ConnectorMeta(
        slug="ledger",
        name="Ledger",
        category=Category.MONEY,
        auth=AuthType.BUILT_IN,
        unlocks="Track income and expenses, including recurring ones like hosting.",
        setup_minutes=1,
        phase=1,
        capabilities=frozenset({C.READ_SPEND, C.READ_REVENUE}),
        requirements=(R.FREE,),
        logo_text="€",
        docs_path="connectors/ledger",
    )
)
register(
    ConnectorMeta(
        slug="stripe",
        name="Stripe",
        category=Category.MONEY,
        auth=AuthType.API_KEY,
        unlocks="Revenue, fees and subscriptions, so cost per customer is always current.",
        setup_minutes=3,
        phase=2,
        capabilities=frozenset({C.READ_REVENUE}),
        requirements=(R.API_KEY,),
        logo_text="St",
        docs_path="connectors/stripe",
    )
)
register(
    ConnectorMeta(
        slug="csv_import",
        name="CSV import",
        category=Category.MONEY,
        auth=AuthType.UPLOAD,
        unlocks="Import a bank or card export to fill in everything else.",
        setup_minutes=3,
        phase=2,
        capabilities=frozenset({C.READ_SPEND, C.READ_REVENUE}),
        requirements=(R.FREE,),
        logo_text="CSV",
        docs_path="connectors/csv-import",
    )
)

# --- Work --------------------------------------------------------------------
register(
    ConnectorMeta(
        slug="board",
        name="Board",
        category=Category.WORK,
        auth=AuthType.BUILT_IN,
        unlocks="A Kanban board whose cards link to the alerts and posts they are about.",
        setup_minutes=1,
        phase=1,
        requirements=(R.FREE,),
        logo_text="KB",
        docs_path="connectors/board",
    )
)

recommend(ProjectKind.WEB_APP, ("uptime_probe", "django_sdk", "resend", "ga4"))
recommend(ProjectKind.API, ("uptime_probe", "django_sdk", "status_endpoint", "resend"))
recommend(ProjectKind.MOBILE_APP, ("django_sdk", "heartbeat", "instagram", "tiktok"))
recommend(ProjectKind.SHOP, ("uptime_probe", "ga4", "instagram", "meta_ads"))
