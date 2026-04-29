"""
Image tools — multimodal + generation.

Tools:
  generate_image   — DALL-E 3 / Stable Diffusion image generation
  describe_image   — describe what's in an image (multimodal LLM)
  resize_image     — resize an image using PIL or ImageMagick
  convert_image    — convert image format (PNG→JPG, etc.)
  list_images      — list image files in a directory
  image_info       — get metadata about an image file
"""

from __future__ import annotations

import logging
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger("cogman.image")


def generate_image(prompt: str, output_path: str = "", size: str = "1024x1024", quality: str = "standard") -> str:
    """
    Generate an image from a text prompt.

    Uses DALL-E 3 if OPENAI_API_KEY is set, otherwise tries
    local Stable Diffusion (if COGMAN_SD_URL is set).
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    sd_url = os.getenv("COGMAN_SD_URL", "")

    if not output_path:
        import tempfile
        output_path = tempfile.mktemp(suffix=".png")

    if api_key:
        return _generate_dalle(prompt, output_path, size, quality, api_key)
    elif sd_url:
        return _generate_sd(prompt, output_path, sd_url)
    else:
        return (
            "Image generation requires:\n"
            "  OPENAI_API_KEY  — for DALL-E 3 (openai.com)\n"
            "  COGMAN_SD_URL   — for local Stable Diffusion (e.g. http://localhost:7860)"
        )


def _generate_dalle(prompt: str, output_path: str, size: str, quality: str, api_key: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        image_url = response.data[0].url
        revised_prompt = getattr(response.data[0], "revised_prompt", "")

        # Download the image
        with urllib.request.urlopen(image_url) as r:
            data = r.read()
        with open(output_path, "wb") as f:
            f.write(data)

        result = f"Image generated: {output_path}"
        if revised_prompt and revised_prompt != prompt:
            result += f"\nRevised prompt: {revised_prompt}"
        return result
    except ImportError:
        return "Install openai: pip install openai"
    except Exception as e:
        return f"DALL-E error: {e}"


def _generate_sd(prompt: str, output_path: str, sd_url: str) -> str:
    """Generate image via Stable Diffusion WebUI API (AUTOMATIC1111 or ComfyUI)."""
    import json, urllib.request
    endpoint = f"{sd_url.rstrip('/')}/sdapi/v1/txt2img"
    payload = {
        "prompt": prompt,
        "steps": 30,
        "width": 512,
        "height": 512,
        "cfg_scale": 7,
    }
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read())
        images = result.get("images", [])
        if not images:
            return "SD returned no images."
        import base64
        img_data = base64.b64decode(images[0])
        with open(output_path, "wb") as f:
            f.write(img_data)
        return f"Image generated via Stable Diffusion: {output_path}"
    except Exception as e:
        return f"Stable Diffusion error: {e}"


def describe_image(image_path: str, question: str = "") -> str:
    """
    Describe or answer questions about an image using a multimodal LLM.
    Requires ANTHROPIC_API_KEY or OPENAI_API_KEY.
    """
    if not os.path.exists(image_path):
        return f"File not found: {image_path}"

    import base64, mimetypes
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    media_type, _ = mimetypes.guess_type(image_path)
    if not media_type:
        ext = Path(image_path).suffix.lower()
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                      "gif": "image/gif", "webp": "image/webp"}.get(ext[1:], "image/png")

    prompt_text = question or "Describe this image in detail."

    # Try Anthropic (best multimodal)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                        {"type": "text", "text": prompt_text},
                    ],
                }],
            )
            return response.content[0].text
        except Exception as e:
            log.error("Anthropic vision error: %s", e)

    # Try OpenAI GPT-4V
    oai_key = os.getenv("OPENAI_API_KEY", "")
    if oai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=oai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                        {"type": "text", "text": prompt_text},
                    ],
                }],
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            log.error("OpenAI vision error: %s", e)

    return "Image analysis requires ANTHROPIC_API_KEY or OPENAI_API_KEY."


def resize_image(input_path: str, output_path: str = "", width: int = 0, height: int = 0, scale: float = 0.0) -> str:
    """Resize an image to given dimensions or scale factor."""
    if not os.path.exists(input_path):
        return f"File not found: {input_path}"
    if not output_path:
        output_path = input_path

    # Try PIL
    try:
        from PIL import Image
        img = Image.open(input_path)
        orig_w, orig_h = img.size
        if scale:
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
        elif width and height:
            new_w, new_h = width, height
        elif width:
            new_h = int(orig_h * (width / orig_w))
            new_w = width
        elif height:
            new_w = int(orig_w * (height / orig_h))
            new_h = height
        else:
            return "Specify width, height, or scale."
        img = img.resize((new_w, new_h), Image.LANCZOS)
        img.save(output_path)
        return f"Resized to {new_w}x{new_h}: {output_path}"
    except ImportError:
        pass

    # Try ImageMagick
    size_arg = f"{width}x{height}" if width and height else (f"{width}" if width else f"x{height}")
    if scale:
        size_arg = f"{int(scale*100)}%"
    result = subprocess.run(
        ["convert", input_path, "-resize", size_arg, output_path],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"Resized: {output_path}"
    return "Resize failed. Install: pip install Pillow  or  sudo apt install imagemagick"


def convert_image(input_path: str, output_path: str, quality: int = 90) -> str:
    """Convert image to a different format."""
    if not os.path.exists(input_path):
        return f"File not found: {input_path}"
    try:
        from PIL import Image
        img = Image.open(input_path)
        ext = Path(output_path).suffix.lower()
        if ext in (".jpg", ".jpeg"):
            img = img.convert("RGB")
            img.save(output_path, quality=quality)
        else:
            img.save(output_path)
        return f"Converted: {input_path} → {output_path}"
    except ImportError:
        pass
    result = subprocess.run(["convert", input_path, output_path], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Converted: {output_path}"
    return "Conversion failed. Install: pip install Pillow  or  sudo apt install imagemagick"


def list_images(directory: str = ".", extensions: str = "png,jpg,jpeg,gif,webp,bmp,svg") -> str:
    """List image files in a directory."""
    exts = {f".{e.strip()}" for e in extensions.split(",")}
    path = Path(directory).expanduser()
    if not path.is_dir():
        return f"Not a directory: {directory}"
    images = sorted([f for f in path.iterdir() if f.suffix.lower() in exts])
    if not images:
        return f"No images found in {directory}"
    lines = [f"Images in {directory} ({len(images)}):"]
    for img in images:
        size = img.stat().st_size
        lines.append(f"  {img.name} ({size // 1024} KB)")
    return "\n".join(lines)


def image_info(path: str) -> str:
    """Get metadata about an image file."""
    if not os.path.exists(path):
        return f"File not found: {path}"
    stat = os.stat(path)
    info = [
        f"File: {path}",
        f"Size: {stat.st_size // 1024} KB ({stat.st_size} bytes)",
    ]
    try:
        from PIL import Image, ExifTags
        img = Image.open(path)
        info.append(f"Format: {img.format}")
        info.append(f"Mode: {img.mode}")
        info.append(f"Dimensions: {img.width}x{img.height} px")
        exif = img._getexif() if hasattr(img, "_getexif") else None
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag in ("Make", "Model", "DateTime", "Software"):
                    info.append(f"EXIF {tag}: {value}")
    except ImportError:
        result = subprocess.run(["identify", path], capture_output=True, text=True)
        if result.returncode == 0:
            info.append(result.stdout.strip())
    except Exception as e:
        info.append(f"(could not read metadata: {e})")
    return "\n".join(info)


def register_image_tools(registry):
    registry.register(
        "generate_image",
        generate_image,
        "Generate an image from a text prompt using DALL-E 3 or Stable Diffusion",
        parameters={
            "prompt": {"type": "string", "description": "Image description/prompt", "required": True},
            "output_path": {"type": "string", "description": "Where to save the image"},
            "size": {"type": "string", "description": "Image size: 1024x1024, 1792x1024, 1024x1792"},
            "quality": {"type": "string", "description": "Quality: standard or hd"},
        },
    )
    registry.register(
        "describe_image",
        describe_image,
        "Describe an image or answer questions about it using multimodal AI",
        parameters={
            "image_path": {"type": "string", "description": "Path to image file", "required": True},
            "question": {"type": "string", "description": "Specific question about the image"},
        },
    )
    registry.register(
        "resize_image",
        resize_image,
        "Resize an image to specified dimensions or scale",
        parameters={
            "input_path": {"type": "string", "description": "Input image path", "required": True},
            "output_path": {"type": "string", "description": "Output path (default: overwrite)"},
            "width": {"type": "integer", "description": "Target width in pixels"},
            "height": {"type": "integer", "description": "Target height in pixels"},
            "scale": {"type": "number", "description": "Scale factor (0.5 = 50%)"},
        },
    )
    registry.register(
        "convert_image",
        convert_image,
        "Convert image to a different format (PNG, JPG, WebP, etc.)",
        parameters={
            "input_path": {"type": "string", "description": "Input image path", "required": True},
            "output_path": {"type": "string", "description": "Output path with new extension", "required": True},
            "quality": {"type": "integer", "description": "JPEG quality 1-100 (default 90)"},
        },
    )
    registry.register(
        "list_images",
        list_images,
        "List image files in a directory",
        parameters={
            "directory": {"type": "string", "description": "Directory to list (default: current)"},
            "extensions": {"type": "string", "description": "Comma-separated extensions (default: png,jpg,jpeg,gif,webp)"},
        },
    )
    registry.register(
        "image_info",
        image_info,
        "Get metadata and EXIF info about an image file",
        parameters={
            "path": {"type": "string", "description": "Path to image file", "required": True},
        },
    )
