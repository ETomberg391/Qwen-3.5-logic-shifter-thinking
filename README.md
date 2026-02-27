# Qwen 3.5 Logic Shifter

A dynamic reasoning control system for Qwen 3.5 that enables real-time switching between thinking and non-thinking modes via simple tags in your system prompts.

## What It Does

This project provides a **Flask-based interceptor** that sits between your OpenAI-compatible client and llama.cpp's llama-server. It detects special tags in your system prompt and automatically:

1. **Adjusts sampling parameters** (temperature, top_p, penalties) optimized for each mode
2. **Controls thinking token injection** via a custom Jinja chat template
3. **Routes all traffic** transparently to your llama-server instance

### Available Modes

| Mode | Tag | Temperature | Top P | Top K | Min P | Presence | Repeat | Best For |
|------|-----|-------------|-------|-------|-------|----------|--------|----------|
| **General Thinking** | *(default)* | 1.0 | 0.95 | 20 | 0.0 | 1.5 | 1.0 | Creative tasks, exploration |
| **Non-Thinking** | `/no_thinking` | 0.7 | 0.8 | 20 | 0.0 | 1.5 | 1.0 | Fast responses, simple Q&A |
| **Precise** | `/precise` | 0.6 | 0.95 | 20 | 0.0 | 0.0 | 1.0 | Code generation, web development |

> **Note**: These parameters are optimized for llama.cpp's sampling pipeline. `repeat_penalty` is the native llama.cpp key (not OpenAI's `frequency_penalty`).

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
# Default: port 8189, forwarding to localhost:8188 (prompt trigger mode)
python interceptor.py

# Alias trigger mode (detect from model name)
python interceptor.py --trigger alias --verbose

# Any trigger mode (alias or prompt, prompt wins)
python interceptor.py --trigger any --verbose

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
Trigger mode: prompt
  Detecting modes from system prompt tags
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

## Trigger Modes

The interceptor supports three trigger modes for detecting which reasoning mode to use. Set the mode with the `--trigger` argument:

```bash
python interceptor.py --trigger alias    # Detect from model name
python interceptor.py --trigger prompt   # Detect from system prompt (default)
python interceptor.py --trigger any      # Both: alias first, prompt overrides
```

### Mode: `prompt` (Default)

Detects mode from tags in the system prompt. This is the **default behavior** and matches the original implementation.

```python
response = client.chat.completions.create(
    model="qwen3.5",
    messages=[
        {"role": "system", "content": "/no_thinking You are helpful"},
        {"role": "user", "content": "Hello!"}
    ]
)
```

### Mode: `alias`

Detects mode from the **model name**. Perfect for clients like Aider that don't allow custom system prompt modifications.

**Supported Patterns:**

| Pattern in Model Name | Injected Command | Mode |
|----------------------|------------------|------|
| `nonthinking`, `no_thinking`, `non-thinking`, `fast`, `instruct` | `/no_thinking` | Non-Thinking |
| `precise`, `coder`, `code`, `webdev` | `/precise` | Precise |
| `thinking`, `reasoning`, `think` | `/thinking` | Explicit Thinking |

**Example:**

Start the interceptor:
```bash
python interceptor.py --trigger alias --verbose
```

Client request:
```python
response = client.chat.completions.create(
    model="openai/Qwen3.5-NonThinking",  # Contains "NonThinking"
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ]
)
```

The interceptor will:
1. Detect "NonThinking" in the model name
2. Inject `/no_thinking` into the system prompt
3. Apply non-thinking sampling parameters

### Mode: `any`

Checks **both** alias and prompt. Explicit tags in the system prompt take priority over model name detection.

**Priority Order:**
1. Check model name for alias patterns
2. Check system prompt for explicit tags
3. If both found: **prompt tags win** (override alias)

**Example:**

```python
# Case 1: Alias only - triggers non-thinking
response = client.chat.completions.create(
    model="qwen-nonthinking",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Case 2: Both alias and prompt - prompt wins!
response = client.chat.completions.create(
    model="qwen-nonthinking",  # Would trigger non-thinking
    messages=[
        {"role": "system", "content": "/precise You are a coder"},  # But this wins!
        {"role": "user", "content": "Write Python"}
    ]
)
```

### Aider Integration Example

Aider doesn't allow injecting custom tags into system prompts, so use `--trigger alias`:

**1. Create Aider model config** (`.aider.model.settings.yml`):
```yaml
- name: openai/Qwen3.5-Thinking
  edit_format: diff
  aliases:
    - qwen-think

- name: openai/Qwen3.5-NonThinking
  edit_format: diff
  aliases:
    - qwen-fast
```

**2. Start interceptor with alias mode:**
```bash
python interceptor.py --trigger alias --verbose
```

**3. Launch Aider:**
```bash
# For thinking mode
export OPENAI_API_KEY="someapitest"
export OPENAI_API_BASE="http://localhost:8189/v1"
aider --model qwen-think

# For non-thinking mode (fast)
aider --model qwen-fast
```

---

## How It Works

### Interceptor Logic Flow

1. **Receive Request**: Client sends to `localhost:8189/v1/chat/completions`
2. **Detect Mode** (based on `--trigger` setting):
   - `prompt`: Check system prompt for `/no_thinking`, `/precise` tags
   - `alias`: Check model name for patterns (e.g., "NonThinking"), inject command into system prompt
   - `any`: Check both; prompt tags override alias detection
3. **Inject Parameters**: Override sampling params based on detected mode
4. **Forward**: Send modified request to llama-server on port 8188
5. **Return Response**: Stream result back to client unchanged

### Jinja Template Logic

```
System Prompt: "/no_thinking Be direct"
       ↓
Interceptor detects "/no_thinking"
       ↓
Sets sampling: temp=0.7, top_p=0.8, top_k=20, min_p=0.0, presence=1.5, repeat=1.0
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

Edit [`interceptor.py`](interceptor.py:28-57) to adjust the default parameters:

```python
# Default parameters for General Thinking mode
params = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
    "repeat_penalty": 1.0  # llama.cpp native key (not frequency_penalty)
}

# Override for /no_thinking mode
params.update({
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
    "repeat_penalty": 1.0
})
```

**Parameter Reference:**
- `temperature`: Randomness (0.0-2.0, higher = more creative)
- `top_p`: Nucleus sampling threshold (0.0-1.0)
- `top_k`: Limit vocabulary to top K tokens (1-100)
- `min_p`: Dynamic minimum probability filter (0.0-1.0)
- `presence_penalty`: Penalize token reuse across the entire prompt (0.0-2.0)
- `repeat_penalty`: Multiplier for repeated tokens (1.0 = no penalty, >1.0 = penalize)

### Custom Mode Tags

To add a new mode (e.g., `/creative`):

1. **In [`interceptor.py`](interceptor.py:29-34):**
```python
elif "/creative" in system_content:
    mode_name = "MODE: CREATIVE"
    params.update({"temperature": 1.2, "top_p": 0.99})
```

2. **In [`interceptor.py`](interceptor.py):**
```python
elif "/creative" in system_content:
    mode_name = "MODE: CREATIVE"
    params.update({
        "temperature": 1.2,
        "top_p": 0.99,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0
    })
```

3. **In [`qwen3-5-logic-shifting.jinja`](chat-template/qwen3-5-logic-shifting.jinja:50-52):**
```jinja
{%- if '/creative' in sys_text_check %}
    {%- set ns_flags.disable_thinking = false %}
{%- endif %}
```

4. **Strip tag in lines 73 and 81:**
```jinja
|replace('/no_thinking','')|replace('/creative','')
```

---

## Troubleshooting

### Interceptor not detecting modes
- Ensure the tag is in the **first** system message
- Check that `/no_thinking` is lowercase and includes the underscore
- Run with `--verbose` to see detected mode and source in console
- Verify your `--trigger` mode matches your usage:
  - Use `--trigger alias` if detecting from model names
  - Use `--trigger prompt` (default) if using system prompt tags
  - Use `--trigger any` for maximum flexibility

### Alias mode not working
- Ensure `--trigger alias` or `--trigger any` is set
- Check model name contains a recognized pattern (e.g., "NonThinking", "fast", "precise")
- Use `--verbose` to see if the alias is detected and command injected
- Case-insensitive matching is used, so "NONTHINKING" and "nonthinking" both work

### Prompt tags override not working in `any` mode
- Ensure the explicit tag is at the **start** of the system prompt
- Only `/no_thinking`, `/precise`, and `/thinking` are recognized as override tags
- Use `--verbose` to see which source was used (should show "prompt" as source)

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
