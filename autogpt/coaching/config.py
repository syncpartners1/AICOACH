"""Configuration for the ABN Consulting AI Co-Navigator."""
import os

from autogpt.singleton import Singleton


class CoachingConfig(metaclass=Singleton):
    """Reads coaching-specific settings from environment variables."""

    def __init__(self):
        self.coach_name: str = os.getenv("COACHING_COACH_NAME", "Adi Ben Nesher")
        self.coach_calendly_url: str = os.getenv(
            "COACHING_COACH_CALENDLY_URL", "https://calendly.com/abn_consulting/30min"
        )
        self.alert_red_threshold: int = int(os.getenv("COACHING_ALERT_RED_THRESHOLD", "25"))
        self.alert_yellow_threshold: int = int(os.getenv("COACHING_ALERT_YELLOW_THRESHOLD", "40"))
        self.api_key: str = os.getenv("COACHING_API_KEY", "")
        self.supabase_url: str = os.getenv("SUPABASE_URL", "")
        self.supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
        # Claude LLM settings
        self.llm_model: str = os.getenv("COACHING_LLM_MODEL", "claude-haiku-4-5-20251001")
        self.llm_temperature: float = float(os.getenv("COACHING_LLM_TEMPERATURE", "0.7"))
        # Google OAuth (.strip() guards against copy-paste whitespace in Railway env vars)
        self.google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        self.google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        # Full callback URL — must match exactly what is registered in Google Cloud Console
        # Example: https://your-app.railway.app/auth/google/callback
        self.google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
        # Telegram bot
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_bot_username: str = os.getenv("TELEGRAM_BOT_USERNAME", "")
        # WhatsApp Business Cloud API
        self.whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        self.whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "997470790125080")
        self.whatsapp_business_account_id: str = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "1140904578083674")
        self.whatsapp_app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
        self.whatsapp_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        # Facebook / Meta Login
        self.facebook_app_id: str = os.getenv("FACEBOOK_APP_ID", "2003921883519698")
        self.facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET", "")
        # Facebook User ID allowed as admin (leave blank to allow any valid FB login)
        self.admin_facebook_id: str = os.getenv("ADMIN_FACEBOOK_ID", "")
        # Admin phone for WhatsApp OTP login (E.164 without +, e.g. 972501234567)
        self.admin_whatsapp_phone: str = os.getenv("ADMIN_WHATSAPP_PHONE", "")
        # Admin settings
        self.admin_telegram_id: int = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
        self.admin_user_id: str = os.getenv("ADMIN_USER_ID", "")
        # Admin web dashboard credentials
        self.admin_username: str = os.getenv("ADMIN_USERNAME", "Adi")
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "")
        # Demo page — separate key so the main API key isn't exposed in the browser
        self.demo_key: str = os.getenv("COACHING_DEMO_KEY", "")
        # Public URL of this service (used to build the demo page's API_BASE).
        # RAILWAY_PUBLIC_DOMAIN is the bare domain, e.g. cnbot.up.railway.app
        _domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
        if _domain and not _domain.startswith("http"):
            _domain = f"https://{_domain}"
        self.public_url: str = _domain or os.getenv("PUBLIC_URL", "")
        # Scheduler (calendar booking service)
        self.scheduler_url: str = os.getenv("SCHEDULER_URL", "https://abn-sch.up.railway.app")
        self.scheduler_api_key: str = os.getenv("SCHEDULER_API_KEY", "")
        self.scheduler_timezone: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Jerusalem")
        # EmailJS (server-side REST API)
        self.emailjs_service_id: str = os.getenv("EMAILJS_SERVICE_ID", "service_a85ap2g")
        self.emailjs_template_invite: str = os.getenv("EMAILJS_TEMPLATE_INVITE", "CNAPP_Invite")
        self.emailjs_template_welcome: str = os.getenv("EMAILJS_TEMPLATE_WELCOME", "CNAPP_Welcome")
        self.emailjs_public_key: str = os.getenv("EMAILJS_PUBLIC_KEY", "nxguxr-WfLhUpXOhn")
        self.emailjs_private_key: str = os.getenv("EMAILJS_PRIVATE_KEY", "")

    def validate(self) -> None:
        """Raise if required env vars are missing."""
        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_key:
            missing.append("SUPABASE_SERVICE_KEY")
        if not self.api_key:
            missing.append("COACHING_API_KEY")
        if not os.getenv("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


# Module-level singleton instance
coaching_config = CoachingConfig()
