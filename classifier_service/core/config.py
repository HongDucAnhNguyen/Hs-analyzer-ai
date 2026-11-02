import os
from dotenv import load_dotenv
import logfire

def setup_environment():
    """
    Load environment variables, configure logging and API key.
    With Pydantic AI, just configure Logfire - it will automatically instrument all LLM calls.
    """
    load_dotenv()

    # Get Logfire token from environment variable
    logfire_token = os.getenv("LOGFIRE_TOKEN")
    
    if not logfire_token:
        print("⚠️ LOGFIRE_TOKEN not set in .env file. Logfire monitoring disabled.")
        print("   To enable monitoring, add LOGFIRE_TOKEN to your .env file")
        print("   Classifier service will continue without Logfire monitoring")
        return
    
    # Enable message content capture to log prompts and responses
    os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
    
    environment = os.getenv("LOGFIRE_ENVIRONMENT", "production")
    
    try:
        # Configure Logfire
        logfire.configure(
            token=logfire_token,
            environment=environment,
            send_to_logfire='if-token-present',
            console=False  # Disable console logging to reduce noise
        )
        
        # ONLY instrument Pydantic AI - don't instrument httpx, fastapi, etc.
        # This keeps logs cleaner, focusing only on LLM calls
        logfire.instrument_pydantic_ai()
        
        print("✅ Logfire configured successfully")
        print(f"📊 Environment: {environment}")
        print("✅ Pydantic AI instrumentation enabled")
        print("📊 LLM calls will be logged to: https://logfire.pydantic.dev/")
    except Exception as e:
        print(f"⚠️ Logfire setup failed: {e}")
        print("Classifier service will continue without Logfire monitoring")
