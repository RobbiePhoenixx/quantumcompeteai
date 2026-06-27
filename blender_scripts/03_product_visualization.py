"""
Product Visualization — Studio Setup
=====================================
Ask Claude: "Create a professional product render of [your product]"
Run inside Blender: Scripting tab → Run Script
Then: Render > Render Image

What this does: Sets up a professional studio environment —
white backdrop, three-point lighting, camera angle —
ready to drop any 3D product model into.
"""

import bpy

# ── Clean scene ───────────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ── White studio backdrop (infinite floor + curved wall) ─────────────────────
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.object
floor.name = "StudioFloor"

bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 5, 5))
wall = bpy.context.object
wall.rotation_euler = (1.5708, 0, 0)
wall.name = "StudioWall"

# White material for backdrop
white = bpy.data.materials.new("StudioWhite")
white.use_nodes = True
bsdf = white.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (1, 1, 1, 1)
    bsdf.inputs["Roughness"].default_value  = 0.8
floor.data.materials.append(white)
wall.data.materials.append(white)

# ── Product placeholder (replace with your actual model) ─────────────────────
bpy.ops.mesh.primitive_cylinder_add(radius=0.8, depth=2.0, location=(0, 0, 1))
product = bpy.context.object
product.name = "Product"

product_mat = bpy.data.materials.new("ProductMaterial")
product_mat.use_nodes = True
prod_bsdf = product_mat.node_tree.nodes.get("Principled BSDF")
if prod_bsdf:
    prod_bsdf.inputs["Base Color"].default_value  = (0.05, 0.05, 0.05, 1.0)
    prod_bsdf.inputs["Metallic"].default_value    = 0.9
    prod_bsdf.inputs["Roughness"].default_value   = 0.1
product.data.materials.append(product_mat)

# ── Three-point lighting (professional studio setup) ─────────────────────────
# Key light (main, bright)
bpy.ops.object.light_add(type='AREA', location=(3, -3, 5))
key = bpy.context.object
key.data.energy = 500
key.data.size   = 3
key.rotation_euler = (0.8, 0, 0.8)

# Fill light (softer, opposite side)
bpy.ops.object.light_add(type='AREA', location=(-3, -2, 3))
fill = bpy.context.object
fill.data.energy = 150
fill.data.size   = 4

# Rim light (behind product, adds edge glow)
bpy.ops.object.light_add(type='SPOT', location=(0, 4, 4))
rim = bpy.context.object
rim.data.energy = 300
rim.rotation_euler = (2.4, 0, 0)

# ── Camera ────────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(4, -4, 3))
cam = bpy.context.object
cam.rotation_euler = (1.1, 0, 0.785)
bpy.context.scene.camera = cam

# Square format (good for Instagram product posts)
bpy.context.scene.render.resolution_x = 1080
bpy.context.scene.render.resolution_y = 1080

print("Studio setup complete!")
print("Tip: Select the 'Product' object and swap it for your actual 3D model.")
print("Then go to Render > Render Image.")
