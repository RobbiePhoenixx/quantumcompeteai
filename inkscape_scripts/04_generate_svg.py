"""
Generate SVG with Python → Open in Inkscape
============================================
Ask Claude: "Make me a flyer for [event/product]"
Claude writes this script → run it → open the output in Inkscape to fine-tune.

Usage:
  python3 inkscape_scripts/04_generate_svg.py
  Then open output.svg in Inkscape, or double-click to preview in VS Code.
"""

import subprocess
import os

# ── Build your SVG as a string ────────────────────────────────────────────────
def make_promo_flyer(
    headline="LIMITED OFFER",
    subheadline="Get started today",
    body="Join Quantum Compete AI and transform your business\nwith AI-powered tools built for the modern entrepreneur.",
    cta="Book a free call → quantumcompeteai.com",
    output_file="inkscape_scripts/promo_flyer.svg"
):
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">

  <!-- Background -->
  <rect width="1080" height="1080" fill="#17181C"/>

  <!-- Gold corner accents -->
  <line x1="60"  y1="60"  x2="160" y2="60"  stroke="#C7A35A" stroke-width="3"/>
  <line x1="60"  y1="60"  x2="60"  y2="160" stroke="#C7A35A" stroke-width="3"/>
  <line x1="1020" y1="60"  x2="920" y2="60"  stroke="#C7A35A" stroke-width="3"/>
  <line x1="1020" y1="60"  x2="1020" y2="160" stroke="#C7A35A" stroke-width="3"/>
  <line x1="60"  y1="1020" x2="160" y2="1020" stroke="#C7A35A" stroke-width="3"/>
  <line x1="60"  y1="1020" x2="60"  y2="920"  stroke="#C7A35A" stroke-width="3"/>
  <line x1="1020" y1="1020" x2="920" y2="1020" stroke="#C7A35A" stroke-width="3"/>
  <line x1="1020" y1="1020" x2="1020" y2="920" stroke="#C7A35A" stroke-width="3"/>

  <!-- Brand -->
  <text x="540" y="120" font-family="Arial" font-size="22" fill="#C7A35A"
        text-anchor="middle" letter-spacing="6">QUANTUM COMPETE AI</text>

  <!-- Headline -->
  <text x="540" y="400" font-family="Georgia, serif" font-size="100"
        font-weight="bold" fill="#C7A35A" text-anchor="middle">{headline}</text>

  <!-- Sub-headline -->
  <text x="540" y="490" font-family="Georgia, serif" font-size="44"
        fill="#FFFFFF" text-anchor="middle">{subheadline}</text>

  <!-- Divider -->
  <line x1="200" y1="540" x2="880" y2="540" stroke="#C7A35A" stroke-width="1" opacity="0.5"/>

  <!-- Body text -->
  <text x="540" y="620" font-family="Arial" font-size="32"
        fill="#AAAAAA" text-anchor="middle">{body.split(chr(10))[0]}</text>
  <text x="540" y="665" font-family="Arial" font-size="32"
        fill="#AAAAAA" text-anchor="middle">{body.split(chr(10))[1] if chr(10) in body else ""}</text>

  <!-- CTA -->
  <rect x="190" y="780" width="700" height="90" rx="8" fill="#C7A35A"/>
  <text x="540" y="838" font-family="Arial" font-size="30" font-weight="bold"
        fill="#17181C" text-anchor="middle">{cta}</text>

</svg>"""

    with open(output_file, "w") as f:
        f.write(svg)
    print(f"SVG saved to: {output_file}")

    # Auto-open in Inkscape if available
    if os.path.exists("/Applications/Inkscape.app"):
        subprocess.Popen(["open", "-a", "Inkscape", output_file])
        print("Opening in Inkscape...")
    else:
        print("Open the file manually in Inkscape or preview it in VS Code.")


if __name__ == "__main__":
    make_promo_flyer()
