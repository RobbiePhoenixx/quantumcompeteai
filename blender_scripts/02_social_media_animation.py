"""
Social Media Animation — Spinning Logo
=======================================
Ask Claude: "Animate my logo spinning for a 3-second Instagram reel"
Run inside Blender: Scripting tab → Run Script
Then: Render > Render Animation  (outputs to /tmp/render/)

What this does: Takes a 3D object and animates it rotating 360°
over 90 frames (3 seconds at 30fps) — perfect for social content.
"""

import bpy
import math

# ── Scene settings ────────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end   = 90      # 3 seconds at 30fps
scene.render.fps  = 30

# Vertical (9:16) format for Instagram/TikTok
scene.render.resolution_x = 1080
scene.render.resolution_y = 1920

# Output folder
scene.render.filepath = "/tmp/blender_render/frame_"
scene.render.image_settings.file_format = 'PNG'

# ── Clean scene and add a cube as placeholder ─────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
obj = bpy.context.object
obj.name = "LogoObject"

# ── Gold material ─────────────────────────────────────────────────────────────
mat = bpy.data.materials.new(name="Gold")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.6, 0.1, 1.0)
    bsdf.inputs["Metallic"].default_value   = 1.0
    bsdf.inputs["Roughness"].default_value  = 0.2
obj.data.materials.append(mat)

# ── Keyframe animation — full 360° spin ───────────────────────────────────────
obj.rotation_euler = (0, 0, 0)
obj.keyframe_insert(data_path="rotation_euler", frame=1)

obj.rotation_euler = (0, 0, math.radians(360))
obj.keyframe_insert(data_path="rotation_euler", frame=90)

# Make it spin at constant speed (linear interpolation)
for fcurve in obj.animation_data.action.fcurves:
    for kp in fcurve.keyframe_points:
        kp.interpolation = 'LINEAR'

# ── Camera ────────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(0, -5, 0))
cam = bpy.context.object
cam.rotation_euler = (1.5708, 0, 0)   # 90° — looking straight at the object
bpy.context.scene.camera = cam

# ── Light ─────────────────────────────────────────────────────────────────────
bpy.ops.object.light_add(type='SUN', location=(5, -5, 8))
bpy.context.object.data.energy = 4

print("Animation ready! Hit Render > Render Animation to export frames.")
print(f"Frames will be saved to: {scene.render.filepath}")
