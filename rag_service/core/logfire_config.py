"""
Logfire configuration for tracking token usage and monitoring with cost tracking.
Enables Pydantic AI instrumentation to capture LLM costs automatically.
"""
import os
import logfire
from dotenv import load_dotenv

load_dotenv()


def setup_logfire():
    """
    Configure Logfire for the application with Pydantic AI instrumentation.
    This will automatically track:
    - LLM token usage
    - Cost per API call
    - Latency metrics
    - Message content (prompts and responses)
    """
    # Get Logfire token from environment
    logfire_token = os.getenv("LOGFIRE_TOKEN")
    environment = os.getenv("LOGFIRE_ENVIRONMENT", "development")
    
    if not logfire_token:
        print("⚠️ LOGFIRE_TOKEN not set. Logfire monitoring disabled.")
        return
    
    try:
        # Enable capturing of message content for LLM calls
        # This is CRITICAL for seeing prompts, responses, and costs
        os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
        
        # Configure Logfire
        logfire.configure(
            token=logfire_token,
            environment=environment,
            send_to_logfire='if-token-present',
            console=False  # Disable console logging to reduce noise
        )
        
        # Instrument Pydantic AI - this automatically tracks all LLM calls with costs!
        # This will capture: token usage, costs, latency for all Pydantic AI agents
        logfire.instrument_pydantic_ai()
        
        print("✅ Logfire configured successfully")
        print(f"📊 Environment: {environment}")
        print("📊 Pydantic AI instrumentation enabled")
        print("💰 Cost tracking enabled for all LLM calls")
        print("🔗 View logs at: https://logfire.pydantic.dev/")
        
    except Exception as e:
        print(f"⚠️ Logfire setup failed: {e}")
        print("Application will continue without Logfire monitoring")
