# Inkscape Scripts — How to Use

## What Is Inkscape?
Inkscape is a free professional vector graphics editor — like Adobe Illustrator.
Vector graphics never get blurry no matter how big you make them.
Perfect for logos, business cards, social media graphics, and flyers.

---

## The Files in This Folder

| File | What It Is | Open With |
|---|---|---|
| `01_logo.svg` | Your Quantum Compete AI logo | Inkscape or VS Code preview |
| `02_social_media_post.svg` | 9:16 Instagram/TikTok post template | Inkscape |
| `03_business_card.svg` | Printable business card | Inkscape |
| `04_generate_svg.py` | Python script that builds SVGs | Run in terminal |

---

## Three Ways to Work

### Way 1 — Open and Edit Directly in Inkscape
1. Open **Inkscape** from your Applications folder
2. File → Open → pick any `.svg` file from this folder
3. Click on any text to edit it
4. File → Export → Export as PNG when done

### Way 2 — Preview in VS Code
1. Click any `.svg` file in VS Code
2. It shows a live preview on the right side (powered by the SVG Preview extension)
3. Edit the SVG code on the left, preview updates live on the right

### Way 3 — Ask Claude to Build Something New
Tell Claude what you want in plain English, for example:

- *"Make me a gold and black Instagram post that says 'Free Strategy Call' with a button at the bottom"*
- *"Design a flyer for my AI coaching program at $500/month, dark background, gold text"*
- *"Create a LinkedIn banner for Quantum Compete AI, 1584x396 pixels"*

Claude will write the SVG code. Paste it into a new `.svg` file and open in Inkscape.

---

## Exporting for Use

**For social media:** File → Export → Export as PNG → set 1080px wide
**For print:** File → Save As → PDF (keeps it crisp at any size)
**For web:** Use the SVG file directly (smallest file size, perfectly sharp)

---

## Running the Python Generator

```bash
cd "/Users/robbiephoenixx/Documents/All Coding Projects/all-in-one-app"
python3 inkscape_scripts/04_generate_svg.py
```

This creates a promo flyer SVG and auto-opens it in Inkscape.
Ask Claude to customize the text, colors, or layout.
