"""ComfyUI / Forge のモデルの「種別」(checkpoints / vae / loras …)の推定。

推定はパスとファイル名だけで行う(ファイルの中身は見ない)。順番: ① フォルダ名 ② ファイル名 ③ どれでもなければ checkpoint。
役割(role)は、種別の定義(machine.json の categories の roles)で、サービスの種別に結び付く。
"""
import re

from ...core.config import categories


ROLE_DIRS = {
    "checkpoint": {"checkpoints", "checkpoint", "stable-diffusion"},
    "diffusion": {"diffusion_models", "diffusion_model", "unet", "transformer"},
    "textenc": {"text_encoders", "text_encoder"},
    "clip": {"clip"},
    "vae": {"vae"},
    "lora": {"loras", "lora"},
    "controlnet": {"controlnet"},
    "embedding": {"embeddings", "embedding"},
    "upscale": {"upscale_models", "esrgan", "upscalers"},
    "clipvision": {"clip_vision"},
    "animatediff": {"animatediff_models"},
    "animatediff_lora": {"animatediff_motion_lora"},
    "style": {"style_models"},
    "latent_upscale": {"latent_upscale_models"},
    "audio": {"audio_encoders"},
}


def guess_role(path):
    parts = [x.lower() for x in path.split("/")]
    for seg in reversed(parts[:-1]):
        for role, names in ROLE_DIRS.items():
            if seg in names:
                return role
    n = parts[-1]
    if "lora" in n:
        return "lora"
    if "vae" in n or n.startswith(("ae.", "taesd", "taef")):
        return "vae"
    if re.search(r"clip_[lg]\b|clip_[lg][._]", n):
        return "clip"
    if re.search(r"t5|umt5|qwen\d*vl|text_encoder|_te[._]|mistral|gemma", n):
        return "textenc"
    if re.search(r"controlnet|control_", n):
        return "controlnet"
    if re.search(r"esrgan|upscal|^4x|^2x|swinir", n):
        return "upscale"
    if "embedding" in n:
        return "embedding"
    if n.endswith(".gguf"):
        return "diffusion"
    return "checkpoint"


def guess_category(service, path):
    cats_ = categories(service)
    role = guess_role(path)
    for c in cats_:
        if role in c.get("roles", []):
            return c["key"]
    return cats_[0]["key"] if cats_ else None
