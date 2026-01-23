import requests
import json
import os
import argparse
import sys
import time


def check_health(base_url):
    """Check if the service is up and running."""
    url = f"{base_url}/docs"
    print(f"[*] Checking service health at {url}...")
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print(f"[+] Service is UP. Status code: {response.status_code}")
            return True
        else:
            print(
                f"[-] Service returned unexpected status code: {response.status_code}"
            )
            return False
    except requests.exceptions.ConnectionError:
        print("[-] Could not connect to the service. Is it running?")
        return False
    except Exception as e:
        print(f"[-] Health check failed: {e}")
        return False


def test_tts(base_url, output_file="tests/output_test.wav", ref_audio="example_en.wav"):
    print(f"\n[*] Testing TTS generation at {base_url}/tts...")

    payload = {
        "text": "你好，这是一个自动化测试请求。",
        "text_lang": "zh",
        "ref_audio_path": ref_audio,
        "streaming_mode": False,
    }
    print(f"[*] Payload: {json.dumps(payload, ensure_ascii=False)}")

    try:
        # Increase timeout to 300s for first-time initialization
        response = requests.post(f"{base_url}/tts", json=payload, timeout=300)

        if response.status_code == 200:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(response.content)
            print(
                f"[+] TTS success! Audio saved to {output_file} ({len(response.content)} bytes)"
            )
            return True
        else:
            print(f"[-] Request failed with status code: {response.status_code}")
            try:
                print(f"[-] Error message: {response.json()}")
            except:
                print(f"[-] Raw response: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"[-] TTS test failed with exception: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test GPT-SoVITS API")
    parser.add_argument(
        "--url", default="http://localhost:3333", help="Base URL of the API"
    )
    parser.add_argument(
        "--ref",
        default="【默认】万圣节快乐哦~☆_听说今天商场有卖一日限定的饰品呢，_老师要不要和我一起去购物呀？_zh.wav",
        help="Name of reference audio file in the mapped volume",
    )
    parser.add_argument(
        "--out", default="tests/output_test.wav", help="Path to save the output audio"
    )

    args = parser.parse_args()

    print("=== GPT-SoVITS API Tester ===")

    if not check_health(args.url):
        sys.exit(1)

    if test_tts(args.url, args.out, args.ref):
        print("\n=== ALL TESTS PASSED ===")
        sys.exit(0)
    else:
        print("\n=== TESTS FAILED ===")
        sys.exit(1)
