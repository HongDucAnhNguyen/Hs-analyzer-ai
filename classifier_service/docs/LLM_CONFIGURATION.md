# LLM Configuration Guide

Ứng dụng phân loại mã HS hiện đã được refactor để sử dụng **Pydantic AI**, cho phép dễ dàng chuyển đổi giữa nhiều LLM providers mà không cần thay đổi code.

## Supported Providers

- **Google Gemini** (default)
- **OpenAI GPT**
- Có thể mở rộng thêm: Anthropic Claude, Groq, DeepSeek, v.v.

## Configuration

### 1. Sử dụng Environment Variables

Cấu hình LLM provider thông qua các biến môi trường:

```bash
# Chọn provider (mặc định: gemini)
export LLM_PROVIDER=gemini  # hoặc openai

# Chọn model cụ thể (tùy chọn)
export LLM_MODEL_NAME=gemini-2.0-flash-lite  # cho Gemini
# hoặc
export LLM_MODEL_NAME=gpt-4o  # cho OpenAI

# Temperature setting (mặc định: 0.0)
export LLM_TEMPERATURE=0.0
```

### 2. API Keys

Đảm bảo bạn đã cài đặt API key phù hợp:

**Cho Gemini:**
```bash
export GOOGLE_GENAI_API_KEY=your-gemini-api-key
```

**Cho OpenAI:**
```bash
export OPENAI_API_KEY=your-openai-api-key
```

## Ví dụ Sử dụng

### Chạy với Gemini (Default)

```bash
cd classification
bash run.sh
```

### Chuyển sang OpenAI

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your-openai-api-key
cd classification
bash run.sh
```

### Sử dụng model cụ thể

```bash
# Sử dụng Gemini Pro
export LLM_PROVIDER=gemini
export LLM_MODEL_NAME=gemini-1.5-pro
export GOOGLE_GENAI_API_KEY=your-key
bash run.sh

# Sử dụng GPT-4
export LLM_PROVIDER=openai
export LLM_MODEL_NAME=gpt-4
export OPENAI_API_KEY=your-key
bash run.sh
```

## Kiến trúc

### Trước (Hard-coded Gemini)

```python
import google.generativeai as genai

model = genai.GenerativeModel(
    'gemini-2.0-flash-lite',
    generation_config={
        "response_mime_type": "application/json",
        "response_schema": gemini_section_schema,
        "temperature": 0
    }
)
response = model.generate_content(prompt)
```

### Sau (Flexible với Pydantic AI)

```python
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

# Tự động chọn provider dựa trên config
agent = Agent(
    model_string,  # e.g., 'google-gla:gemini-2.0-flash-lite' hoặc 'openai:gpt-4o'
    output_type=SectionClassification,  # Pydantic model tự động
    model_settings=ModelSettings(temperature=0.0)
)
result = agent.run_sync(prompt)
```

## Lợi ích

1. **Linh hoạt**: Chuyển đổi provider chỉ bằng environment variable
2. **Type-safe**: Structured output tự động từ Pydantic models
3. **Đơn giản hóa**: Không cần định nghĩa schema riêng cho từng provider
4. **Mở rộng dễ dàng**: Thêm provider mới chỉ cần update `LLMConfig`
5. **Fallback**: Có thể cấu hình fallback giữa các providers
6. **Cost optimization**: Dễ dàng so sánh chi phí giữa các providers

## Mở rộng Provider Mới

Để thêm provider mới (ví dụ: Anthropic Claude):

1. Cập nhật `classification/core/llm_config.py`:

```python
class LLMProvider(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"  # Thêm mới

class LLMConfig(BaseModel):
    def get_model_string(self) -> str:
        if self.provider == LLMProvider.ANTHROPIC:
            model = self.model_name or "claude-3-5-sonnet-latest"
            return f"anthropic:{model}"
        # ... existing code
```

2. Set environment variables:

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=your-anthropic-api-key
bash run.sh
```

## Testing

Test với các providers khác nhau:

```bash
# Test Gemini
export LLM_PROVIDER=gemini
curl -X POST http://localhost:2222/api/v1/classify/ \
  -H "Content-Type: application/json" \
  -d '{"product_name": "Test Product"}'

# Test OpenAI
export LLM_PROVIDER=openai
curl -X POST http://localhost:2222/api/v1/classify/ \
  -H "Content-Type: application/json" \
  -d '{"product_name": "Test Product"}'
```

## Troubleshooting

### Lỗi: "API key not found"

**Giải pháp:** Đảm bảo bạn đã set đúng environment variable cho provider:
- Gemini: `GOOGLE_GENAI_API_KEY`
- OpenAI: `OPENAI_API_KEY`

### Lỗi: "Model not found"

**Giải pháp:** Kiểm tra tên model trong `LLM_MODEL_NAME` có đúng không.

### Performance khác nhau giữa providers

**Lưu ý:** Mỗi provider có thể có tốc độ và chất lượng khác nhau. Hãy benchmark và chọn provider phù hợp với use case của bạn.

## Best Practices

1. **Development**: Sử dụng Gemini Flash cho tốc độ
2. **Production**: Cân nhắc giữa cost và quality
3. **Fallback**: Cấu hình fallback từ OpenAI sang Gemini để đảm bảo uptime
4. **Monitoring**: Theo dõi token usage và cost cho mỗi provider
5. **Testing**: Test kỹ với mỗi provider trước khi deploy

## References

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [Google Gemini API](https://ai.google.dev/)
- [OpenAI API](https://platform.openai.com/docs/)
