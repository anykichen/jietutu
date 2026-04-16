# -*- coding: utf-8 -*-
"""
生成 SnapFloat 软件图标 (ICO格式)
"""
from PIL import Image, ImageDraw

def create_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        padding = size // 16
        body_left = padding
        body_top = size // 4
        body_right = size - padding
        body_bottom = size * 3 // 4 + size // 8
        draw.rounded_rectangle(
            [body_left, body_top, body_right, body_bottom],
            radius=size // 12,
            fill=(30, 90, 160, 255)
        )

        lens_outer = size // 3
        lens_cx = size // 2
        lens_cy = (body_top + body_bottom) // 2
        lens_radius = lens_outer // 2
        draw.ellipse(
            [lens_cx - lens_radius, lens_cy - lens_radius,
             lens_cx + lens_radius, lens_cy + lens_radius],
            fill=(60, 60, 80, 255)
        )
        lens_inner = lens_radius * 2 // 3
        draw.ellipse(
            [lens_cx - lens_inner, lens_cy - lens_inner,
             lens_cx + lens_inner, lens_cy + lens_inner],
            fill=(100, 160, 230, 255)
        )
        lens_core = lens_radius // 3
        draw.ellipse(
            [lens_cx - lens_core, lens_cy - lens_core,
             lens_cx + lens_core, lens_cy + lens_core],
            fill=(200, 220, 255, 255)
        )

        viewfinder_size = size // 6
        viewfinder_left = size * 3 // 4 - viewfinder_size // 2
        viewfinder_top = body_top - size // 16
        draw.rounded_rectangle(
            [viewfinder_left, viewfinder_top,
             viewfinder_left + viewfinder_size, viewfinder_top + viewfinder_size * 2 // 3],
            radius=size // 32,
            fill=(200, 180, 0, 255)
        )

        images.append(img)

    icon_path = 'app.ico'
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    print(f'Icon created: {icon_path}')

if __name__ == '__main__':
    create_icon()