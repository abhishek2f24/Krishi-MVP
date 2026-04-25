"""
Test Google Gemini vision on a PlantVillage image.
Run: python test_ai.py
"""
import os, base64
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Pick a diseased tomato image from PlantVillage
DATASET_DIR = "PlantVillage"
test_image_path = None
for folder in os.listdir(DATASET_DIR):
    if "Tomato" in folder and "healthy" not in folder.lower():
        folder_path = os.path.join(DATASET_DIR, folder)
        if os.path.isdir(folder_path):
            for f in os.listdir(folder_path):
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    test_image_path = os.path.join(folder_path, f)
                    test_label = folder
                    break
    if test_image_path:
        break

print(f"Image: {test_image_path}")
print(f"Label: {test_label}\n")

with open(test_image_path, "rb") as f:
    image_bytes = f.read()

response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        "What crop disease is shown in this image? Name the crop and disease clearly.",
    ],
)

print("Gemini response:")
print(response.text)
