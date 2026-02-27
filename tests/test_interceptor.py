#!/usr/bin/env python3
"""Test script for Qwen 3.5 Logic Shifter Interceptor Service."""

import argparse
import json
from openai import OpenAI


def create_client(base_url="http://localhost:8189/v1"):
    """Create an OpenAI client pointing to the interceptor."""
    return OpenAI(base_url=base_url, api_key="not-needed")


def test_mode(client, mode_name, system_tag, user_query):
    """Test a specific mode and print results."""
    print(f"\n{'='*60}")
    print(f"Testing: {mode_name}")
    if system_tag:
        print(f"System Tag: {system_tag}")
    print("-"*60)

    messages = []
    
    # Add system message with mode tag if provided
    if system_tag:
        messages.append({
            "role": "system", 
            "content": f"{system_tag} You are a helpful assistant."
        })
    else:
        messages.append({
            "role": "system", 
            "content": "You are a helpful assistant."
        })

    # Add user query
    messages.append({"role": "user", "content": user_query})

    try:
        response = client.chat.completions.create(
            model="qwen3.5",
            messages=messages,
            stream=False  # Non-streaming for cleaner test output
        )

        content = response.choices[0].message.content
        
        print(f"\nResponse:\n{content}")
        
        # Check if thinking tokens appear in output (indicates mode may not be working)
        has_thinking_tokens = "<think>" in content or "</think>" in content
        print(f"\nThinking tokens detected: {has_thinking_tokens}")

    except Exception as e:
        print(f"Error: {e}")


def test_streaming_mode(client, mode_name, system_tag, user_query):
    """Test a specific mode with streaming output."""
    print(f"\n{'='*60}")
    print(f"Testing Streaming: {mode_name}")
    if system_tag:
        print(f"System Tag: {system_tag}")
    print("-"*60)

    messages = [
        {"role": "system", "content": f"{system_tag} You are a helpful assistant." if system_tag else "You are a helpful assistant."},
        {"role": "user", "content": user_query}
    ]

    try:
        response = client.chat.completions.create(
            model="qwen3.5",
            messages=messages,
            stream=True  # Streaming enabled for this test
        )

        print("\nStreaming response:")
        full_content = ""
        
        for chunk in response:
            content_delta = chunk.choices[0].delta.content or ""
            print(content_delta, end="", flush=True)
            full_content += content_delta
        
        print()  # Newline after streaming completes

    except Exception as e:
        print(f"Error: {e}")


def test_precise_mode(client):
    """Test precise mode for code generation."""
    test_mode(
        client=client, 
        mode_name="Precise Mode (Code Generation)", 
        system_tag="/precise", 
        user_query="Write a Python function that calculates Fibonacci numbers efficiently using memoization."
    )


def run_all_tests():
    """Run all test scenarios."""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="Test the Qwen 3.5 Logic Shifter Interceptor")
    parser.add_argument("--base-url", default="http://localhost:8189/v1", help="Interceptor base URL (default: http://localhost:8189/v1)")
    parser.add_argument("--streaming", action="store_true", help="Run streaming tests instead of non-streaming")
    args = parser.parse_args()

    print("="*60)
    print("Qwen 3.5 Logic Shifter - Interceptor Test Suite")
    print("="*60)
    
    # Check if interceptor is running first
    try:
        import requests as req_lib
        
        resp = req_lib.get(f"{args.base_url.replace('/v1', '')}/version", timeout=2) 
        print(f"\n✓ Interceptor appears to be responding at {args.base_url}")
        
    except Exception as e:
        print(f"\n⚠ Warning: Could not verify interceptor is running.")
        print(f"  Error: {e}")
        print("\nMake sure to start the interceptor first:")
        print("  python interceptor.py --verbose")

    # Create client with custom base URL if provided
    client = create_client(args.base_url)

    if args.streaming:
        # Run streaming tests
        test_streaming_mode(
            client=client, 
            mode_name="General Thinking (Streaming)", 
            system_tag=None, 
            user_query="Explain the concept of recursion in simple terms."
        )

        test_streaming_mode(
            client=client, 
            mode_name="Non-Thinking Fast Mode (Streaming)", 
            system_tag="/no_thinking", 
            user_query="What is 2 + 2?"
        )

    else:
        # Run non-streaming tests
        
        # Test 1: General Thinking Mode (Default)
        test_mode(
            client=client, 
            mode_name="General Thinking Mode (Default)", 
            system_tag=None, 
            user_query="Explain the concept of recursion in simple terms."
        )

        # Test 2: Non-Thinking Fast Mode - Simple Q&A should be quick and direct
        test_mode(
            client=client, 
            mode_name="Non-Thinking Fast Mode", 
            system_tag="/no_thinking", 
            user_query="What is the capital of France?"
        )

        # Test 3: Non-Thinking Fast Mode - Math question (should be direct)
        test_mode(
            client=client, 
            mode_name="Non-Thinking Fast Mode (Math)", 
            system_tag="/no_thinking", 
            user_query="Calculate: 15 × 8 + 42 ÷ 7"
        )

        # Test 4: Precise Mode - Code generation should be accurate
        test_precise_mode(client)

        # Test 5: General Thinking with creative prompt (should show reasoning)
        test_mode(
            client=client, 
            mode_name="General Thinking Mode (Creative)", 
            system_tag=None, 
            user_query="Design a simple algorithm to sort a list of numbers. Explain your approach."
        )

    print("\n" + "="*60)
    print("Test suite completed!")
    print("="*60)


if __name__ == "__main__":
    run_all_tests()