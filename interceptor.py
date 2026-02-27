import argparse
import json
import re
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# ============================================================================
# CONFIGURATION: Model Alias Mapping
# ============================================================================
# Maps model name patterns (case-insensitive) to command tags
MODEL_ALIAS_MAP = {
    # Non-thinking patterns -> /no_thinking
    "nonthinking": "/no_thinking",
    "no_thinking": "/no_thinking",
    "non-thinking": "/no_thinking",
    "not-thinking": "/no_thinking",
    "fast": "/no_thinking",
    "instruct": "/no_thinking",
    # Precise patterns -> /precise
    "precise": "/precise",
    "coder": "/precise",
    "code": "/precise",
    "webdev": "/precise",
    # Explicit thinking patterns -> /thinking (forces thinking mode)
    "thinking": "/thinking",
    "reasoning": "/thinking",
    "think": "/thinking",
}

# ============================================================================
# CONFIGURATION: Mode Parameters
# ============================================================================
MODE_PARAMS = {
    "/no_thinking": {
        "mode_name": "MODE: NON-THINKING / INSTRUCT",
        "source": "non-thinking",
        "params": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.0
        }
    },
    "/precise": {
        "mode_name": "MODE: THINKING (Precise WebDev)",
        "source": "precise",
        "params": {
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "repeat_penalty": 1.0
        }
    },
    "/thinking": {
        "mode_name": "MODE: THINKING (General)",
        "source": "thinking",
        "params": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.0
        }
    },
    "default": {
        "mode_name": "MODE: THINKING (General)",
        "source": "default",
        "params": {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.0
        }
    }
}

# ============================================================================
# Mode Detection Functions
# ============================================================================

def detect_mode_from_alias(model_name):
    """
    Detect mode from model name by checking for alias patterns.
    
    Args:
        model_name: The model field from the request (e.g., "openai/Qwen3.5-NonThinking")
    
    Returns:
        tuple: (command, mode_info_dict) or (None, None) if no match
    """
    if not model_name:
        return None, None
    
    model_lower = model_name.lower()
    
    for pattern, command in MODEL_ALIAS_MAP.items():
        if pattern in model_lower:
            return command, MODE_PARAMS.get(command, MODE_PARAMS["default"])
    
    return None, None


def detect_mode_from_prompt(system_content):
    """
    Detect mode from system prompt content by checking for explicit tags.
    
    Args:
        system_content: The content of the system message
    
    Returns:
        tuple: (command, mode_info_dict) or (None, None) if no match
    """
    if not system_content:
        return None, None
    
    # Check for explicit tags in priority order
    if "/no_thinking" in system_content:
        return "/no_thinking", MODE_PARAMS["/no_thinking"]
    elif "/precise" in system_content:
        return "/precise", MODE_PARAMS["/precise"]
    elif "/thinking" in system_content:
        return "/thinking", MODE_PARAMS["/thinking"]
    
    return None, None


def inject_command_into_system_prompt(data, command):
    """
    Inject a command tag into the system prompt if not already present.
    
    Args:
        data: The request data dict with "messages" list
        command: The command to inject (e.g., "/no_thinking")
    
    Returns:
        bool: True if injection was performed, False otherwise
    """
    messages = data.get("messages", [])
    
    # Find system message
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            content = msg.get("content", "")
            # Only inject if command is not already at the start
            if not content.strip().startswith(command):
                data["messages"][i]["content"] = f"{command} {content}"
                return True
            return False
    
    # No system message found, create one
    data["messages"].insert(0, {
        "role": "system",
        "content": f"{command} You are a helpful assistant."
    })
    return True


def get_mode_and_params(data, trigger_mode):
    """
    Main mode detection logic based on trigger mode setting.
    
    Args:
        data: The request data dict
        trigger_mode: One of "alias", "prompt", "any"
    
    Returns:
        tuple: (mode_name, params, source_info)
            - mode_name: Human-readable mode name
            - params: Sampling parameters dict
            - source_info: Dict with 'source' (alias/prompt/default) and 'command'
    """
    messages = data.get("messages", [])
    system_content = next(
        (msg.get("content", "") for msg in messages if msg.get("role") == "system"),
        ""
    )
    model_name = data.get("model", "")
    
    alias_command = None
    alias_mode_info = None
    prompt_command = None
    prompt_mode_info = None
    
    # Always detect both for 'any' mode, or the specific one requested
    if trigger_mode in ("alias", "any"):
        alias_command, alias_mode_info = detect_mode_from_alias(model_name)
    
    if trigger_mode in ("prompt", "any"):
        prompt_command, prompt_mode_info = detect_mode_from_prompt(system_content)
    
    # Determine final mode based on trigger_mode
    if trigger_mode == "alias":
        # Alias only: use alias detection, inject command into prompt
        if alias_command:
            inject_command_into_system_prompt(data, alias_command)
            return (
                alias_mode_info["mode_name"],
                alias_mode_info["params"],
                {"source": "alias", "command": alias_command, "model": model_name}
            )
        # No alias match, use default
        default = MODE_PARAMS["default"]
        return default["mode_name"], default["params"], {"source": "default", "command": None}
    
    elif trigger_mode == "prompt":
        # Prompt only: use existing logic
        if prompt_command:
            return (
                prompt_mode_info["mode_name"],
                prompt_mode_info["params"],
                {"source": "prompt", "command": prompt_command}
            )
        # No prompt match, use default
        default = MODE_PARAMS["default"]
        return default["mode_name"], default["params"], {"source": "default", "command": None}
    
    elif trigger_mode == "any":
        # Any: Check alias first, then prompt. Prompt overrides alias.
        
        # If explicit prompt tag found, it always wins
        if prompt_command:
            return (
                prompt_mode_info["mode_name"],
                prompt_mode_info["params"],
                {"source": "prompt", "command": prompt_command}
            )
        
        # No explicit prompt tag, check alias
        if alias_command:
            inject_command_into_system_prompt(data, alias_command)
            return (
                alias_mode_info["mode_name"],
                alias_mode_info["params"],
                {"source": "alias", "command": alias_command, "model": model_name}
            )
        
        # Neither found, use default
        default = MODE_PARAMS["default"]
        return default["mode_name"], default["params"], {"source": "default", "command": None}
    
    # Fallback to default
    default = MODE_PARAMS["default"]
    return default["mode_name"], default["params"], {"source": "default", "command": None}


# ============================================================================
# Argument Parsing
# ============================================================================

def get_args():
    # Build epilog with model aliases and mode parameters
    epilog = """
MODEL ALIAS MAPPINGS (--trigger alias or any):
  Pattern in Model Name      -> Injected Command
  ---------------------      ------------------
  nonthinking, no_thinking   -> /no_thinking
  non-thinking, not-thinking -> /no_thinking
  fast, instruct             -> /no_thinking
  precise, coder, code       -> /precise
  webdev                     -> /precise
  thinking, reasoning, think -> /thinking

MODE PARAMETERS:
  Command        Mode Name                      Temp   TopP   Presence
  -------        ---------                      ----   ----   --------
  /no_thinking   MODE: NON-THINKING / INSTRUCT  0.7    0.8    1.5
  /precise       MODE: THINKING (Precise)       0.6    0.95   0.0
  /thinking      MODE: THINKING (General)       1.0    0.95   1.5
  (default)      MODE: THINKING (General)       1.0    0.95   1.5

TRIGGER MODES:
  alias  - Detect mode from model name patterns only
  prompt - Detect mode from system prompt tags only (default)
  any    - Check both; explicit prompt tags override alias detection

EXAMPLES:
  # Default prompt mode
  python interceptor.py --verbose

  # Alias mode (detect from model name)
  python interceptor.py --trigger alias --verbose

  # Any mode with custom ports
  python interceptor.py --trigger any --port 9000 --llm-port 8080 --verbose

For more information: https://github.com/yourusername/qwen-3.5-logic-shifter
"""

    parser = argparse.ArgumentParser(
        description="Llama-Server Proxy Interceptor with Trigger Modes",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--verbose", action="store_true", help="Print detailed request and mode info")
    parser.add_argument("--port", type=int, default=8189, help="Proxy port (default: 8189)")
    parser.add_argument("--llm-port", type=int, default=8188, help="llama-server port (default: 8188)")
    parser.add_argument("--llm-host", type=str, default="localhost", help="llama-server host (default: localhost)")
    parser.add_argument(
        "--trigger",
        type=str,
        choices=["alias", "prompt", "any"],
        default="prompt",
        help=(
            "Trigger mode for detecting reasoning mode: "
            "'alias' detects from model name (e.g., 'NonThinking' -> /no_thinking), "
            "'prompt' detects from system prompt tags (default), "
            "'any' checks both with prompt tags taking priority"
        )
    )
    return parser.parse_args()


args = get_args()

# Config: Your llama-server destination
LLAMA_SERVER_URL = f"http://{args.llm_host}:{args.llm_port}"


# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/v1/chat/completions', methods=['POST'])
def intercepted_chat():
    data = request.json
    
    # Get mode and parameters based on trigger setting
    mode_name, params, source_info = get_mode_and_params(data, args.trigger)
    
    # Apply parameters to request data
    data.update(params)
    
    # Verbose logging
    if args.verbose:
        model_name = request.json.get("model", "unknown")
        print(f"\n{'='*60}")
        print(f">>> INTERCEPTED: {mode_name}")
        print(f">>> Trigger Mode: {args.trigger}")
        print(f">>> Source: {source_info['source']}")
        if source_info.get('command'):
            print(f">>> Command: {source_info['command']}")
        if source_info.get('model'):
            print(f">>> Model: {source_info['model']}")
        print(f">>> Parameters applied: {json.dumps(params, indent=2)}")
        print(f"{'='*60}")
    
    headers = {k: v for k, v in request.headers if k.lower() != 'host'}
    resp = requests.post(f"{LLAMA_SERVER_URL}/v1/chat/completions", json=data, headers=headers, stream=True)
    return Response(resp.iter_content(chunk_size=1024), status=resp.status_code, content_type=resp.headers.get('Content-Type'))


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    url = f"{LLAMA_SERVER_URL}/{path}"
    
    if args.verbose:
        print(f"--- BRIDGE: {request.method} /{path}")

    # Forward the request exactly as it came in
    resp = requests.request(
        method=request.method,
        url=url,
        headers={k: v for k, v in request.headers if k.lower() != 'host'},
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        stream=True
    )

    return Response(
        resp.iter_content(chunk_size=1024),
        status=resp.status_code,
        content_type=resp.headers.get('Content-Type')
    )


if __name__ == '__main__':
    print(f"Interceptor/Bridge active on port {args.port} -> {LLAMA_SERVER_URL}")
    print(f"Trigger mode: {args.trigger}")
    if args.trigger == "alias":
        print("  Detecting modes from model name patterns")
    elif args.trigger == "prompt":
        print("  Detecting modes from system prompt tags")
    elif args.trigger == "any":
        print("  Detecting from model name or prompt (prompt tags take priority)")
    app.run(host='0.0.0.0', port=args.port, threaded=True)
