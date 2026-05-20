

from google import genai
from google.genai import types

client = genai.Client()

PROMPT = """
Process the audio file and generate a detailed transcription.

Requirements:
1. Identify distinct speakers (e.g., Speaker 1, Speaker 2, or names if context allows).
2. Provide accurate timestamps for each segment (Format: MM:SS).
3. Detect the primary language code of each segment (e.g., zh, en, ja).
"""


def stt(audio_path) -> str:
    autio_file = client.files.upload(file=str(audio_path))

    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=[
            types.Content(
                parts=[
                    types.Part(file_data=types.FileData(file_uri=autio_file.uri)),
                    types.Part(text=PROMPT),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    'segments': types.Schema(
                        type=types.Type.ARRAY,
                        description='List of transcribed segments with speaker and timestamp.',
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                'speaker': types.Schema(type=types.Type.STRING),
                                'timestamp': types.Schema(type=types.Type.STRING),
                                'content': types.Schema(type=types.Type.STRING),
                                'lang_code': types.Schema(type=types.Type.STRING),
                            },
                            required=['speaker', 'timestamp', 'content', 'lang_code'],
                        ),
                    ),
                },
                required=['segments'],
            ),
        ),
    )

    return response.text
