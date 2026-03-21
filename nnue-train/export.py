"""Binary weight export for C++ inference."""

import os
import struct

import torch

from .model import GameNNUE

# Quantization constants (must match C++ compute_quant.hpp)
QA = 255  # FT accumulator scale (int16)
QA_HIDDEN = 127  # hidden activation scale (uint8)
QB = 64  # dense weight scale (int8)
QAH_QB = QA_HIDDEN * QB  # 8128


def export_binary_weights(model: GameNNUE, path: str, gcfg: dict) -> None:
    """Export float32 weights for C++ inference."""
    ps_size = gcfg["ps_size"]
    version = 1 if model.feature_size == ps_size else 2
    sd = model.state_dict()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"MCNN")
        f.write(struct.pack("<i", version))
        f.write(struct.pack("<i", model.feature_size))
        f.write(struct.pack("<i", model.accum_size))
        f.write(struct.pack("<i", model.l1_size))
        f.write(struct.pack("<i", model.l2_size))

        # FT: always export in Linear format (accum, feat) → (feat, accum) for C++
        ft = model.get_linear_ft_state()
        ft_w = ft["ft.weight"].detach().cpu().float().t().contiguous()
        f.write(ft_w.numpy().tobytes())
        ft_b = ft["ft.bias"].detach().cpu().float().contiguous()
        f.write(ft_b.numpy().tobytes())

        for name in [
            "l1.weight",
            "l1.bias",
            "l2.weight",
            "l2.bias",
            "out.weight",
            "out.bias",
        ]:
            tensor = sd[name].detach().cpu().float().contiguous()
            f.write(tensor.numpy().tobytes())

    total_bytes = os.path.getsize(path)
    print(f"  Exported float weights to {path} ({total_bytes} bytes)")
    if model.use_policy:
        print("  Note: Policy head weights NOT exported (C++ support pending)")


def export_quantized_weights(model: GameNNUE, path: str, gcfg: dict) -> None:
    """Export quantized int16/int8 weights for C++ SIMD inference."""
    ps_size = gcfg["ps_size"]
    version = (1 if model.feature_size == ps_size else 2) + 10
    sd = model.state_dict()

    def quant_i16(t, scale):
        return torch.clamp(torch.round(t * scale), -32768, 32767).to(torch.int16)

    def quant_i8(t, scale):
        return torch.clamp(torch.round(t * scale), -128, 127).to(torch.int8)

    def quant_i32(t, scale):
        return torch.clamp(torch.round(t * scale), -(2**31), 2**31 - 1).to(torch.int32)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"MCNN")
        f.write(struct.pack("<i", version))
        f.write(struct.pack("<i", model.feature_size))
        f.write(struct.pack("<i", model.accum_size))
        f.write(struct.pack("<i", model.l1_size))
        f.write(struct.pack("<i", model.l2_size))

        ft = model.get_linear_ft_state()
        ft_w = ft["ft.weight"].detach().cpu().float().t().contiguous()
        f.write(quant_i16(ft_w, QA).numpy().tobytes())
        ft_b = ft["ft.bias"].detach().cpu().float().contiguous()
        f.write(quant_i16(ft_b, QA).numpy().tobytes())

        for w_name, b_name in [
            ("l1.weight", "l1.bias"),
            ("l2.weight", "l2.bias"),
            ("out.weight", "out.bias"),
        ]:
            w = sd[w_name].detach().cpu().float().t().contiguous()
            f.write(quant_i8(w, QB).numpy().tobytes())
            b = sd[b_name].detach().cpu().float().contiguous()
            f.write(quant_i32(b, QAH_QB).numpy().tobytes())

    total_bytes = os.path.getsize(path)
    ft_w_float = ft["ft.weight"].detach().cpu().float()
    ft_w_range = ft_w_float.abs().max().item()
    l1_w_float = sd["l1.weight"].detach().cpu().float()
    l1_w_range = l1_w_float.abs().max().item()

    print(f"  Exported quantized weights to {path} ({total_bytes} bytes)")
    print(
        f"  FT weight range: [{-ft_w_range:.4f}, {ft_w_range:.4f}] "
        f"(QA={QA}, resolution={1/QA:.4f})"
    )
    print(
        f"  L1 weight range: [{-l1_w_range:.4f}, {l1_w_range:.4f}] "
        f"(QB={QB}, clipped={int((l1_w_float.abs() > 127/QB).sum())})"
    )
    if model.use_policy:
        print("  Note: Policy head weights NOT exported (C++ support pending)")
