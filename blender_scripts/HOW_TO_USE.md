# Blender Scripts — How to Use

## The Big Picture
These scripts let Claude write 3D scenes for you in plain English.
You describe what you want → Claude writes the code → you run it in Blender.

---

## How to Run a Script in Blender

1. Open **Blender** (it's in your Applications folder)
2. At the top, change the workspace to **Scripting**
3. Click **Open** and navigate to this folder
4. Pick a script and click **Open**
5. Hit the **▶ Run Script** button
6. Switch to the **Layout** tab to see what was created
7. Go to **Render > Render Image** to export

---

## The Three Scripts

| Script | What It Makes | Use For |
|---|---|---|
| `01_3d_logo.py` | 3D gold text logo | Profile pictures, thumbnails |
| `02_social_media_animation.py` | Spinning 3D object video | Instagram Reels, TikTok |
| `03_product_visualization.py` | Studio product render | Store listings, ads |

---

## How to Ask Claude to Build Something

Just describe what you want in plain English, for example:

- *"Make a 3D version of my logo that says Quantum Compete AI in gold letters with a dark background"*
- *"Animate a golden trophy spinning for 5 seconds in a 9:16 format for TikTok"*
- *"Create a product render of a black coffee mug with my logo on it"*

Claude will write the Blender Python script and you paste it into Blender's Scripting tab.

---

## VS Code + Blender (Advanced)

The **Blender Development** extension is installed in VS Code.
It lets you write scripts in VS Code and run them in live Blender without copy-pasting.

1. Open VS Code
2. Press `Cmd+Shift+P` → type **Blender: Start**
3. Point it to `/Applications/Blender.app`
4. Write your script in VS Code → press `Cmd+Shift+P` → **Blender: Run Script**
