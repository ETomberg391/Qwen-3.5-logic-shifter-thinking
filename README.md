# Qwen 3.5 Logic Shifter

A dynamic reasoning control system for Qwen 3.5 that enables real-time switching between thinking and non-thinking modes via simple tags in your system prompts.

## What It Does

This project provides a **Flask-based interceptor** that sits between your OpenAI-compatible client and llama.cpp's llama-server. It detects special tags in your system prompt and automatically:

1. **Adjusts sampling parameters** (temperature, top_p, penalties) optimized for each mode
2. **Controls thinking token injection** via a custom Jinja chat template
3. **Routes all traffic** transparently to your llama-server instance

### Available Modes

| Mode | Tag | Temperature | Top P | Best For |
|------|-----|-------------|-------|----------|
| **General Thinking** | *(default)* | 1.0 | 0.95 | Creative tasks, exploration |
| **Non-Thinking** | `/no_thinking` | 0.7 | 0.8 | Fast responses, simple Q&A |
| **Precise** | `/precise` | 0.6 | 0.95 | Code generation, web development |

---

## Project Structure

```
.
├── interceptor.py              # Flask proxy server (port 8189)
├── qwen3-5-logic-shifting.jinja # Custom chat template for llama-server
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Requirements: `flask`, `requests`

---

## Setup

### Step 1: Add the Jinja Template to llama-server

The Jinja template controls how thinking tokens (`<think>...</think>`) are injected into the prompt.

**Option A: Direct Command Line**

When starting llama-server, use the `--chat-template-file` flag:

```bash
./llama-server \
    -m /path/to/qwen3.5-q4_k_m.gguf \
    --chat-template-file /path/to/qwen3-5-logic-shifting.jinja \
    --port 8188
```

**Option B: Convert to GGUF Built-in (Recommended for permanent use)**

If you want the template embedded in your model file:

1. Copy the content of `qwen3-5-logic-shifting.jinja`
2. Use a GGUF metadata editor or re-quantize with the template included
3. Alternatively, use llama.cpp's convert script with `--chat-template` flag

**Option C: API Client Header (if supported)**

Some clients allow passing the template in the request header. Check your client's documentation.

### Step 2: Start the Interceptor

The interceptor must run on a different port than llama-server:

```bash
# Default: port 8189, forwarding to localhost:8188
python interceptor.py

# Custom interceptor port
python interceptor.py --port 9000

# Custom llama-server port (if running on different port)
python interceptor.py --llm-port 8080

# Custom llama-server host (for remote servers)
python interceptor.py --llm-host 192.168.1.100 --llm-port 8080

# Verbose mode (shows mode detection and sampling params)
python interceptor.py --verbose
```

**Output:**
```
Interceptor/Bridge active on port 8189 -> http://localhost:8188
```

### Step 3: Configure Your Client

Point your OpenAI-compatible client to the **interceptor's port**, not llama-server directly:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8189/v1",  # Interceptor port
    api_key="not-needed"
)
```

Or for tools like `curl`:

```bash
curl http://localhost:8189/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5",
    "messages": [{"role": "system", "content": "/no_thinking You are helpful"}, {"role": "user", "content": "Hello!"}]
  }'
```

---

## How to Switch Modes

Simply add the mode tag at the **beginning** of your system prompt:

### Non-Thinking Mode (Fast)

```python
response = client.chat.completions.create(
    model="qwen3.5",
    messages=[
        {"role": "system", "content": "/no_thinking You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ]
)
# → Immediate response, no reasoning tokens
```

### Precise Mode (Code/WebDev)

```python
response = client.chat.completions.create(
    model="qwen3.5",
    messages=[
        {"role": "system", "content": "/precise You are an expert Python developer."},
        {"role": "user", "content": "Write a function to parse JSON."}
    ]
)
# → Conservative sampling, optimized for code accuracy
```

### General Thinking Mode (Default)

```python
response = client.chat.completions.create(
    model="qwen3.5",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum mechanics."}
    ]
)
# → Full reasoning with creative sampling
```

---

## How It Works

### Interceptor Logic Flow

1. **Receive Request**: Client sends to `localhost:8189/v1/chat/completions`
2. **Parse System Prompt**: Extract `messages[0].content` if role is "system"
3. **Detect Tags**: Check for `/no_thinking` or `/precise`
4. **Inject Parameters**: Override sampling params based on detected mode
5. **Forward**: Send modified request to llama-server on port 8188
6. **Return Response**: Stream result back to client unchanged

### Jinja Template Logic

```
System Prompt: "/no_thinking Be direct"
       ↓
Interceptor detects "/no_thinking"
       ↓
Sets sampling: temp=0.7, top_p=0.8
       ↓
Jinja template:
   - Strips "/no_thinking" from output
   - Injects: <|im_start|>assistant\n<think>\n\n</think>\n\n
       ↓
Model sees: "Be direct" → responds immediately (empty think block)
```

---

## Architecture

```
┌─────────────────┐
│     Client      │
│  (Your App/CLI) │
└────────┬────────┘
         │ POST /v1/chat/completions
         │ system: "/no_thinking ..."
         ▼
┌───────────────────────────┐
│      Interceptor          │
│      (Port 8189)          │
│  ┌─────────────────────┐  │
│  │ 1. Parse messages   │  │
│  │ 2. Detect /no_think │  │
│  │ 3. Set sampling:    │  │
│  │    temp=0.7, etc.   │  │
│  └─────────────────────┘  │
└───────────┬───────────────┘
            │ Modified request
            ▼
┌───────────────────────────┐
│     llama-server          │
│      (Port 8188)          │
│  ┌─────────────────────┐  │
│  │ Apply Jinja template│  │
│  │ Strip tag, inject   │  │
│  │ thinking tokens     │  │
│  └─────────────────────┘  │
│            │              │
│            ▼              │
│      ┌──────────┐         │
│      │   GGUF   │         │
│      │   Model  │         │
│      └──────────┘         │
└───────────────────────────┘
            │
            ▼
      Response stream
```

---

## Advanced Configuration

### Custom Sampling Parameters

Edit [`interceptor.py`](interceptor.py:27-34) to adjust the default parameters:

```python
# Default /no_thinking params
params.update({
    "temperature": 0.7,
    "top_p": 0.8,
    "presence_penalty": 1.5
    # Add: "frequency_penalty": 1.0, "top_k": 40, etc.
})
```

### Custom Mode Tags

To add a new mode (e.g., `/creative`):

1. **In [`interceptor.py`](interceptor.py:29-34):**
```python
elif "/creative" in system_content:
    mode_name = "MODE: CREATIVE"
    params.update({"temperature": 1.2, "top_p": 0.99})
```

2. **In [`qwen3-5-logic-shifting.jinja`](qwen3-5-logic-shifting.jinja:50-52):**
```jinja
{%- if '/creative' in sys_text_check %}
    {%- set ns_flags.disable_thinking = false %}
{%- endif %}
```

3. **Strip tag in lines 73 and 81:**
```jinja
|replace('/no_thinking','')|replace('/creative','')
```

---

## Troubleshooting

### Interceptor not detecting modes
- Ensure the tag is in the **first** system message
- Check that `/no_thinking` is lowercase and includes the underscore
- Run with `--verbose` to see detected mode in console

### Thinking tokens still appear with `/no_thinking`
- Verify llama-server is using the Jinja template
- Check template was loaded: look for "chat template" in llama-server startup logs
- Test template directly: `llama-server --chat-template-file ... --verbose`

### Connection refused errors
- Ensure llama-server is running on port 8188 (or update `LLAMA_SERVER_URL`)
- Check firewall rules for ports 8188-8189
- Verify interceptor started successfully (look for "active on port" message)

### Tags appearing in model output
- Jinja template should strip `/no_thinking` automatically
- If visible, verify lines 73 and 81 in the template include the `|replace` filter

---

## Requirements

- **Python**: 3.8+
- **llama.cpp**: llama-server binary with Jinja template support
- **Model**: Qwen 3.5 (or compatible Qwen 3+ models)
- **Memory**: Sufficient RAM/VRAM for your chosen GGUF quantization

---

## License

This project is provided as-is for educational and development purposes.

---

## Credits

- Built for [Qwen 3.5](https://huggingface.co/Qwen) by Alibaba Cloud
- Uses [llama.cpp](https://github.com/ggerganov/llama.cpp) for inference
- Jinja template based on Qwen's official chat format
- Jinja template's modifications from Bartowski and -Ellary- for the main logic shifting.
