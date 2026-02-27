import argparse
import json
import requests
from flask import Flask, request, Response

app = Flask(__name__)

def get_args():
    parser = argparse.ArgumentParser(description="Llama-Server Proxy Interceptor")
    parser.add_argument("--verbose", action="store_true", help="Print detailed request and mode info")
    parser.add_argument("--port", type=int, default=8189, help="Proxy port (default: 8189)")
    parser.add_argument("--llm-port", type=int, default=8188, help="llama-server port (default: 8188)")
    parser.add_argument("--llm-host", type=str, default="localhost", help="llama-server host (default: localhost)")
    return parser.parse_args()

args = get_args()

# Config: Your llama-server destination
LLAMA_SERVER_URL = f"http://{args.llm_host}:{args.llm_port}"

# --- 1. THE INTERCEPTOR (Specific Logic) ---
@app.route('/v1/chat/completions', methods=['POST'])
def intercepted_chat():
    data = request.json
    messages = data.get("messages", [])
    system_content = next((msg.get("content", "") for msg in messages if msg.get("role") == "system"), "")

    # Default: Thinking Mode (General)
    params = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0
    }

    if "/no_thinking" in system_content:
        mode_name = "MODE: NON-THINKING / INSTRUCT"
        params.update({
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.0
        })
    elif "/precise" in system_content:
        mode_name = "MODE: THINKING (Precise WebDev)"
        params.update({
            "temperature": 0.6,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 0.0,
            "repeat_penalty": 1.0
        })
    else:
        mode_name = "MODE: THINKING (General)"

    data.update(params)

    if args.verbose:
        print(f"\n>>> INTERCEPTED: {mode_name}")
        print(f">>> Parameters applied: {json.dumps(params, indent=2)}")

    headers = {k: v for k, v in request.headers if k.lower() != 'host'}
    resp = requests.post(f"{LLAMA_SERVER_URL}/v1/chat/completions", json=data, headers=headers, stream=True)
    return Response(resp.iter_content(chunk_size=1024), status=resp.status_code, content_type=resp.headers.get('Content-Type'))

# --- 2. THE BRIDGE (Transparent Pass-Through) ---
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
    app.run(host='0.0.0.0', port=args.port, threaded=True)