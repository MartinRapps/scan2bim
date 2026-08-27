import argparse
import glob
import os
import shutil
import sys

# Disable torch.compile to avoid massive compilation-induced VRAM spikes (>12GB) on 16GB GPUs
os.environ["TORCH_COMPILE_DISABLE"] = "1"

from contextlib import nullcontext

import cv2
import numpy as np
import torch
from huggingface_hub import login
from PIL import Image


def find_input_video(raw_dir: str) -> str:
    video_files = sorted(glob.glob(os.path.join(raw_dir, "*.mp4")) + glob.glob(os.path.join(raw_dir, "*.mov")))
    if not video_files:
        raise FileNotFoundError(f"No input video found in {raw_dir}")
    return video_files[0]


def extract_frames(video_path: str, out_dir: str, max_side: int, frame_step: int = 1) -> int:
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    frame_idx = 0
    saved_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            if max_side > 0:
                h, w = frame.shape[:2]
                longest = max(h, w)
                if longest > max_side:
                    scale = max_side / float(longest)
                    nw = max(1, int(round(w * scale)))
                    nh = max(1, int(round(h * scale)))
                    frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

            cv2.imwrite(os.path.join(out_dir, f"{saved_idx:05d}.jpg"), frame)
            saved_idx += 1
        frame_idx += 1

    cap.release()
    return saved_idx


def write_mask_from_outputs(frame_idx: int, outputs: dict, masks_dir: str, height: int, width: int) -> int:
    merged = np.zeros((height, width), dtype=np.uint8)

    if isinstance(outputs, dict):
        if "out_obj_ids" in outputs and "out_binary_masks" in outputs:
            obj_ids = outputs["out_obj_ids"]
            masks = outputs["out_binary_masks"]
            if hasattr(obj_ids, "tolist"):
                obj_ids_list = obj_ids.tolist()
            else:
                obj_ids_list = list(obj_ids)
            
            for idx, obj_id in enumerate(obj_ids_list):
                m = masks[idx]
                if hasattr(m, "cpu"):
                    m = m.squeeze().cpu().numpy()
                else:
                    m = np.squeeze(m)
                
                if m.shape != (height, width):
                    try:
                        import cv2
                        m = cv2.resize(m.astype(np.float32), (width, height), interpolation=cv2.INTER_NEAREST)
                    except ImportError:
                        m_pil = Image.fromarray(m.astype(np.uint8)).resize((width, height), resample=Image.NEAREST)
                        m = np.array(m_pil)
                
                cur = (m > 0.5).astype(np.uint8) * 255
                merged = np.maximum(merged, cur)
        else:
            for _, obj_out in outputs.items():
                if not isinstance(obj_out, dict):
                    continue
                m = obj_out.get("masks")
                if m is None:
                    continue
                if hasattr(m, "cpu"):
                    m = m.squeeze().cpu().numpy()
                
                if m.shape != (height, width):
                    try:
                        import cv2
                        m = cv2.resize(m.astype(np.float32), (width, height), interpolation=cv2.INTER_NEAREST)
                    except ImportError:
                        m_pil = Image.fromarray(m.astype(np.uint8)).resize((width, height), resample=Image.NEAREST)
                        m = np.array(m_pil)
                
                cur = (m > 0.5).astype(np.uint8) * 255
                merged = np.maximum(merged, cur)

    Image.fromarray(merged).save(os.path.join(masks_dir, f"frame_{frame_idx:05d}_obj_001.png"))
    return int(np.count_nonzero(merged) > 0)


def clear_png_masks(dir_path: str) -> None:
    if not os.path.isdir(dir_path):
        return
    for name in os.listdir(dir_path):
        if name.endswith(".png") and name.startswith("frame_"):
            os.remove(os.path.join(dir_path, name))


def sanitize_prompt_for_dir(name: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    while "__" in clean:
        clean = clean.replace("__", "_")
    clean = clean.strip("_")
    return clean or "prompt"


def find_input_media(raw_dir: str, input_mode: str) -> tuple[str, str]:
    image_files = sorted(
        glob.glob(os.path.join(raw_dir, "*.jpg"))
        + glob.glob(os.path.join(raw_dir, "*.jpeg"))
        + glob.glob(os.path.join(raw_dir, "*.png"))
    )
    video_files = sorted(glob.glob(os.path.join(raw_dir, "*.mp4")) + glob.glob(os.path.join(raw_dir, "*.mov")))

    if input_mode == "image":
        if not image_files:
            raise FileNotFoundError(f"No image found in {raw_dir}")
        return "image", image_files[0]
    if input_mode == "video":
        if not video_files:
            raise FileNotFoundError(f"No video found in {raw_dir}")
        return "video", video_files[0]

    if image_files:
        return "image", image_files[0]
    if video_files:
        return "video", video_files[0]
    raise FileNotFoundError(f"No supported media found in {raw_dir}")


def infer_media_kind_from_path(media_path: str) -> str:
    lower_path = media_path.lower()
    if lower_path.endswith((".jpg", ".jpeg", ".png")):
        return "image"
    if lower_path.endswith((".mp4", ".mov")):
        return "video"
    raise ValueError(f"Unsupported media extension for input path: {media_path}")


def bpe_vocab_path() -> str:
    import sam3

    return os.path.join(os.path.dirname(sam3.__file__), "assets", "bpe_simple_vocab_16e6.txt.gz")


def mask_tensor_to_uint8(mask_tensor, height: int, width: int) -> np.ndarray:
    if mask_tensor is None:
        return np.zeros((height, width), dtype=np.uint8)

    if hasattr(mask_tensor, "detach"):
        mask_tensor = mask_tensor.detach()
    if hasattr(mask_tensor, "cpu"):
        mask_tensor = mask_tensor.cpu()

    mask_array = np.asarray(mask_tensor)
    if mask_array.size == 0:
        return np.zeros((height, width), dtype=np.uint8)

    if mask_array.ndim == 4:
        mask_array = mask_array[:, 0, :, :]
    if mask_array.ndim == 3:
        mask_array = mask_array.max(axis=0)
    if mask_array.ndim != 2:
        return np.zeros((height, width), dtype=np.uint8)

    return (mask_array > 0.5).astype(np.uint8) * 255


def run_image_segmentation(image_path: str, args) -> int:
    from sam3 import build_sam3_image_model
    from sam3.model.sam3_image_processor import Sam3Processor

    os.makedirs(args.frames_dir, exist_ok=True)
    os.makedirs(args.masks_dir, exist_ok=True)

    image = Image.open(image_path).convert("RGB")
    frame_w, frame_h = image.size
    image.save(os.path.join(args.frames_dir, "00000.jpg"))

    print(f"Input image: {image_path}")
    print(f"Using device: {'cuda' if torch.cuda.is_available() else 'cpu'}")

    from sam3.model_builder import download_ckpt_from_hf
    print("Lade SAM3.1 Checkpoint fuer Bildsegmentierung...")
    ckpt_path = download_ckpt_from_hf(version="sam3.1")
    model = build_sam3_image_model(checkpoint_path=ckpt_path, bpe_path=bpe_vocab_path())
    processor = Sam3Processor(model, confidence_threshold=args.threshold)

    autocast_ctx = torch.autocast(device_type="cuda", dtype=torch.bfloat16) if torch.cuda.is_available() else nullcontext()
    with autocast_ctx:
        state = processor.set_image(image)
        state = processor.set_text_prompt(state=state, prompt=args.prompt)

    mask = mask_tensor_to_uint8(state.get("masks"), frame_h, frame_w)
    out_path = os.path.join(args.masks_dir, "frame_00000_obj_001.png")
    Image.fromarray(mask).save(out_path)

    nonempty_frames = int(np.count_nonzero(mask) > 0)
    print(f"Image mask written to {out_path}")
    if nonempty_frames == 0:
        print("Warnung: Der Bild-Prompt erzeugte keine nicht-leere Maske.")
    return 0


def patch_offload_state_bug_if_needed(predictor):
    if not hasattr(predictor, "model") or not hasattr(predictor.model, "init_state"):
        return

    original_init_state = predictor.model.init_state

    def _init_state_compat(*args, **kwargs):
        kwargs.pop("offload_state_to_cpu", None)
        return original_init_state(*args, **kwargs)

    predictor.model.init_state = _init_state_compat


def main() -> int:
    parser = argparse.ArgumentParser(description="SAM3.1 notebook-style video mask extraction")
    parser.add_argument("--prompt", required=True, type=str)
    parser.add_argument("--input-mode", choices=["auto", "image", "video"], default="video", type=str)
    parser.add_argument("--input-path", default=None, type=str)
    parser.add_argument("--raw-dir", default="/data/01_raw", type=str)
    parser.add_argument("--frames-dir", default="/data/02_frames", type=str)
    parser.add_argument("--masks-dir", default="/data/03_masks", type=str)
    parser.add_argument("--frame-max-side", default=int(os.environ.get("SAM3_FRAME_MAX_SIDE", "768")), type=int)
    parser.add_argument("--frame-step", default=int(os.environ.get("SAM3_FRAME_STEP", "1")), type=int)
    parser.add_argument("--threshold", default=float(os.environ.get("SAM3_DETECTION_THRESHOLD", "0.5")), type=float)
    args = parser.parse_args()

    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        print("HF_TOKEN gefunden. Logge bei HuggingFace ein...")
        login(token=hf_token)

    if args.input_path:
        if not os.path.exists(args.input_path):
            raise FileNotFoundError(f"Explicit input path not found: {args.input_path}")
        media_kind = infer_media_kind_from_path(args.input_path)
        media_path = args.input_path
    else:
        media_kind, media_path = find_input_media(args.raw_dir, args.input_mode)

    if media_kind == "image":
        return run_image_segmentation(media_path, args)

    from sam3.model_builder import build_sam3_multiplex_video_predictor, download_ckpt_from_hf

    os.makedirs(args.frames_dir, exist_ok=True)
    os.makedirs(args.masks_dir, exist_ok=True)

    video_path = media_path
    print(f"Input video: {video_path}")

    num_frames = extract_frames(video_path, args.frames_dir, args.frame_max_side, args.frame_step)
    if num_frames <= 0:
        raise RuntimeError("No frames extracted from input video")

    first = cv2.imread(os.path.join(args.frames_dir, "00000.jpg"), cv2.IMREAD_COLOR)
    if first is None:
        raise RuntimeError("Could not read first extracted frame")
    frame_h, frame_w = first.shape[:2]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    print("Lade SAM3.1 Checkpoint...")
    ckpt_path = download_ckpt_from_hf(version="sam3.1")

    print("Baue Multiplex Predictor (Notebook-Flow)...")
    predictor = build_sam3_multiplex_video_predictor(
        checkpoint_path=ckpt_path,
        use_fa3=False,
        use_rope_real=False,
    )

    # Inject memory constraints to prevent OOM on 16GB GPUs
    try:
        inner_predictor = predictor.predictor if hasattr(predictor, "predictor") else predictor
        if hasattr(inner_predictor, "model"):
            inference_model = inner_predictor.model
            if hasattr(inference_model, "clear_non_cond_mem_around_input"):
                # Disable to avoid AssertionError in newer multiplex models
                inference_model.clear_non_cond_mem_around_input = True
                print("Dynamisch gesetzt: clear_non_cond_mem_around_input = True")
            if hasattr(inference_model, "tracker") and hasattr(inference_model.tracker, "max_cond_frames_in_attn"):
                # Commented out to prevent AssertionError: pos_pred_mask.shape[0] == 1
                # inference_model.tracker.max_cond_frames_in_attn = 2
                print("Max conditioning frames left at default to avoid AssertionError")
            
            # Reduce video grounding batch size to prevent VRAM spikes during text matching
            inference_model.use_batched_grounding = True
            inference_model.batched_grounding_batch_size = 1
            print("Dynamisch gesetzt: batched_grounding_batch_size = 1")
            
            if hasattr(inference_model, "detector"):
                det = inference_model.detector
                det.use_batched_grounding = True
                det.batched_grounding_batch_size = 1
                print("Dynamisch gesetzt: detector batched_grounding_batch_size = 1")
    except Exception as e:
        print(f"Warning: Could not set memory bounds dynamically: {e}")

    session_id = None
    selected_prompt = None
    selected_nonempty_frames = 0
    selected_attempt_dir = None

    autocast_ctx = torch.autocast(device_type="cuda", dtype=torch.bfloat16) if device == "cuda" else nullcontext()
    with autocast_ctx:
        try:
            print(f"Start Session fuer Ordner: {args.frames_dir}...")
            try:
                response = predictor.handle_request(
                    request={
                        "type": "start_session",
                        "resource_path": args.frames_dir,
                        "offload_video_to_cpu": True,
                    }
                )
            except TypeError as e:
                if "offload_state_to_cpu" not in str(e):
                    raise
                print("Kompatibilitaets-Fallback fuer offload_state_to_cpu aktiv.")
                patch_offload_state_bug_if_needed(predictor)
                response = predictor.handle_request(
                    request={
                        "type": "start_session",
                        "resource_path": args.frames_dir,
                        "offload_video_to_cpu": True,
                    }
                )

            session_id = response["session_id"]

            propagation_mode = "full"
            attempt_root = os.path.join(args.masks_dir, "_attempts")
            os.makedirs(attempt_root, exist_ok=True)

            prompt_candidates = [args.prompt, "planter", "plant", "desk"]
            prompts_to_try = []
            seen = set()
            for p in prompt_candidates:
                key = p.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    prompts_to_try.append(p.strip())

            print(
                "Prompt-Fallback aktiv: " + ", ".join(prompts_to_try) +
                f" | mode={propagation_mode} | threshold={args.threshold}"
            )
            fatal_cuda_state = False

            def consume_stream(stream_obj, attempt_dir: str, processed_frames: set):
                nonlocal selected_nonempty_frames
                local_nonempty = 0
                try:
                    for response_stream in stream_obj:
                        fidx = response_stream["frame_index"]
                        # Print precise progress to stdout so the Web UI terminal captures it
                        # Format: Processing frame 15 / 100
                        print(f"Processing frame {fidx + 1} / {num_frames}...", flush=True)
                        local_nonempty += write_mask_from_outputs(
                            frame_idx=fidx,
                            outputs=response_stream.get("outputs", {}),
                            masks_dir=attempt_dir,
                            height=frame_h,
                            width=frame_w,
                        )
                        processed_frames.add(fidx)
                finally:
                    if hasattr(stream_obj, "close"):
                        stream_obj.close()
                selected_nonempty_frames += local_nonempty

            for prompt_text in prompts_to_try:
                if fatal_cuda_state:
                    print("Ueberspringe weitere Prompt-Versuche wegen fatalem CUDA-Zustand in diesem Run.")
                    break

                attempt_dir = os.path.join(attempt_root, sanitize_prompt_for_dir(prompt_text))
                os.makedirs(attempt_dir, exist_ok=True)
                clear_png_masks(attempt_dir)
                processed_frames = set()
                selected_nonempty_frames = 0

                print(f"\n=== Prompt-Versuch: '{prompt_text}' ===")
                _ = predictor.handle_request(
                    request={
                        "type": "reset_session",
                        "session_id": session_id,
                    }
                )

                _ = predictor.handle_request(
                    request={
                        "type": "add_prompt",
                        "session_id": session_id,
                        "frame_index": 0,
                        "text": prompt_text,
                        "output_prob_thresh": args.threshold,
                    }
                )

                print("Propagiere Maske (mode=full)...")
                try:
                    consume_stream(
                        predictor.handle_stream_request(
                            request={
                                "type": "propagate_in_video",
                                "session_id": session_id,
                                "propagation_direction": "forward",
                                "output_prob_thresh": args.threshold,
                            }
                        ),
                        attempt_dir,
                        processed_frames,
                    )
                except RuntimeError as prompt_err:
                    import traceback
                    traceback.print_exc()
                    msg = str(prompt_err)
                    if "out of memory" in msg.lower():
                        print(f"Warnung: CUDA OOM im Full-Mode fuer diesen Prompt: {prompt_err}")
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        fatal_cuda_state = True
                    elif "INTERNAL ASSERT FAILED" in msg and "CUDACachingAllocator" in msg:
                        print("Warnung: CUDA Allocator ist nach Fehler inkonsistent (INTERNAL ASSERT).")
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        fatal_cuda_state = True
                    elif "Tensor sizes:" in msg and "0, 256" in msg and "expanded size" in msg:
                        print("Warnung: Keine trackbaren Objekte fuer diesen Prompt erkannt.")
                    elif "No prompts are received" in msg:
                        print("Warnung: Modell hat den Prompt nicht uebernommen.")
                    else:
                        raise

                for i in range(num_frames):
                    if i not in processed_frames:
                        Image.fromarray(np.zeros((frame_h, frame_w), dtype=np.uint8)).save(
                            os.path.join(attempt_dir, f"frame_{i:05d}_obj_001.png")
                        )

                print(f"Prompt '{prompt_text}' nicht-leere Masken: {selected_nonempty_frames}")
                selected_prompt = prompt_text
                selected_attempt_dir = attempt_dir

                if selected_nonempty_frames > 0:
                    print(f"Treffer gefunden mit Prompt '{prompt_text}'.")
                    break

            if selected_nonempty_frames == 0:
                print("Warnung: Kein Prompt-Versuch lieferte nicht-leere Masken. Point-Fallback ist deaktiviert.")

        finally:
            if session_id is not None:
                _ = predictor.handle_request(
                    request={
                        "type": "close_session",
                        "session_id": session_id,
                    }
                )
                print(f"Session {session_id} geschlossen.")

    clear_png_masks(args.masks_dir)
    if selected_attempt_dir is not None:
        for name in sorted(os.listdir(selected_attempt_dir)):
            if name.endswith(".png") and name.startswith("frame_"):
                shutil.copy2(os.path.join(selected_attempt_dir, name), os.path.join(args.masks_dir, name))

    print(f"Masken in {args.masks_dir} geschrieben.")
    print(f"Ausgewaehlter Prompt: {selected_prompt}")
    print(f"Frames gesamt: {num_frames}, nicht-leere Masken: {selected_nonempty_frames}")

    # Hierarchische STS-Maskengenerierung: Erzeuge small.png, middle.png, default.png
    print("\n=== Starte Generierung der hierarchischen STS-Masken ===")
    kernel_size = 5
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))

    # Schleife über alle Frames
    for i in range(num_frames):
        # Bestimme den Pfad der flat Maske im masks_dir
        flat_mask_path = os.path.join(args.masks_dir, f"frame_{i:05d}_obj_001.png")
        
        # Erstelle den dedizierten Unterordner pro Frame für STS
        frame_folder = os.path.join(args.masks_dir, f"frame_{i:05d}")
        os.makedirs(frame_folder, exist_ok=True)
        
        # Lese die flache Maske ein
        if os.path.exists(flat_mask_path):
            mask_uint8 = cv2.imread(flat_mask_path, cv2.IMREAD_GRAYSCALE)
        else:
            # Sicherheits-Fallback falls Datei nicht existiert: Erzeuge leere Maske
            mask_uint8 = np.zeros((frame_h, frame_w), dtype=np.uint8)
            
        if mask_uint8 is None:
            mask_uint8 = np.zeros((frame_h, frame_w), dtype=np.uint8)

        # default.png: Original-Maske als grosszuegiger Kontext fuer STS
        mask_default = mask_uint8.copy()
        cv2.imwrite(os.path.join(frame_folder, "default.png"), mask_default)

        # middle.png: leicht erodiert, um Randartefakte zu reduzieren
        mask_middle = cv2.erode(mask_uint8, kernel, iterations=1)
        cv2.imwrite(os.path.join(frame_folder, "middle.png"), mask_middle)

        # small.png: staerker erodiert als sicherer Objektkern
        mask_small = cv2.erode(mask_middle, kernel, iterations=1)
        cv2.imwrite(os.path.join(frame_folder, "small.png"), mask_small)

    print("Hierarchische STS-Maskensätze (small, middle, default) wurden erfolgreich erstellt.")

    if selected_nonempty_frames == 0:
        print("Warnung: Prompt wurde verarbeitet, aber es wurden keine nicht-leeren Masken gefunden.")

    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
