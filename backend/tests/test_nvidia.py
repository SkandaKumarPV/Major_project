
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def main():
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv(
        "LLM_BASE_URL",
        "https://integrate.api.nvidia.com/v1"
    )
    model = os.getenv("LLM_MODEL")

    if not api_key or not model:
        raise ValueError(
            "LLM_API_KEY or LLM_MODEL is missing from .env"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=90.0,
    )

    print("Connecting to NVIDIA Nemotron...")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional AI interviewer. "
                    "Give concise, natural conversational responses."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Hello, I am a computer science student "
                    "interested in robotics and artificial intelligence."
                ),
            },
        ],
        temperature=0.6,
        max_tokens=300,
    )

    print("\nNVIDIA CONNECTION SUCCESSFUL")
    print("--------------------------------")
    print("Model:", model)
    print("Response:")
    print(response.choices[0].message.content)
    print("--------------------------------")


if __name__ == "__main__":
    main()
