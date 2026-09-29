"""Generate professional Windows .ico icon for Productify Node executable."""

import os
from PIL import Image, ImageDraw


def create_productify_icon(size=256):
    """Draw a modern dark glassmorphic icon with neon lightning bolt badge."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = size * 0.06
    # Outer squircle / rounded rectangle background
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size * 0.22,
        fill="#0b0e14",
        outline="#1e293b",
        width=int(size * 0.03),
    )

    # Inner subtle glow border
    inner_m = margin + size * 0.03
    draw.rounded_rectangle(
        [inner_m, inner_m, size - inner_m, size - inner_m],
        radius=size * 0.18,
        fill=None,
        outline="#26354a",
        width=int(size * 0.015),
    )

    # Electric Lime Lightning Bolt Points
    scale = size / 256.0
    pts = [
        (140 * scale, 35 * scale),
        (80 * scale, 135 * scale),
        (125 * scale, 135 * scale),
        (105 * scale, 220 * scale),
        (185 * scale, 110 * scale),
        (140 * scale, 110 * scale),
    ]

    # Draw lightning shadow / outer glow
    glow_pts = [(x + 2 * scale, y + 3 * scale) for x, y in pts]
    draw.polygon(glow_pts, fill="#042f2e")

    # Draw neon-lime lightning bolt
    draw.polygon(pts, fill="#c8f04c")

    # Bottom status dot (Emerald Green)
    dot_radius = size * 0.05
    dot_cx = size - margin - size * 0.15
    dot_cy = size - margin - size * 0.15
    draw.ellipse(
        [dot_cx - dot_radius, dot_cy - dot_radius, dot_cx + dot_radius, dot_cy + dot_radius],
        fill="#10b981",
        outline="#0b0e14",
        width=int(size * 0.02),
    )

    return img


def generate_ico_file(output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sizes = [256, 128, 64, 48, 32, 16]
    images = [create_productify_icon(s) for s in sizes]

    # Primary 256x256 image saves the rest as icon sizes
    images[0].save(
        output_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"[*] Generated professional multi-resolution Windows icon at: {output_path}")


if __name__ == "__main__":
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    ico_target = os.path.join(assets_dir, "productify.ico")
    generate_ico_file(ico_target)
