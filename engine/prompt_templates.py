"""
engine/prompt_templates.py — Master Schemas for Generative AI

Contains the comprehensive prompt structures for both Video (motion) and 
Image (static) asset generation to ensure high-fidelity, detailed LLM outputs.
"""

VIDEO_PROMPT_TEMPLATE = {
  "project": {
    "title": "",
    "purpose": "",
    "shot_id": "",
    "sequence_position": "",
    "target_platform": "",
    "aspect_ratio": "9:16",
    "duration_seconds": 8
  },
  "story": {
    "scene": "",
    "story_beat": "",
    "narrative_purpose": "",
    "beginning_state": "",
    "ending_state": "",
    "emotional_goal": ""
  },
  "subject": {
    "primary_subject": "",
    "subject_count": 1,
    "age": "",
    "gender_presentation": "",
    "ethnicity_or_cultural_context": "",
    "face": "",
    "hair": "",
    "skin": "",
    "body_type": "",
    "wardrobe": "",
    "accessories": "",
    "distinctive_features": "",
    "identity_lock": ""
  },
  "character_behavior": {
    "expression": "",
    "emotion": "",
    "pose": "",
    "gaze_direction": "",
    "body_language": "",
    "personality": "",
    "micro_expressions": ""
  },
  "action": {
    "primary_action": "",
    "secondary_action": "",
    "movement_style": "",
    "interaction": "",
    "hand_actions": "",
    "facial_actions": "",
    "object_interaction": "",
    "physical_dynamics": ""
  },
  "environment": {
    "location": "",
    "specific_place": "",
    "background": "",
    "foreground": "",
    "midground": "",
    "architecture": "",
    "surface_materials": "",
    "props": [],
    "environmental_details": "",
    "time_of_day": "",
    "season": "",
    "weather": "",
    "atmosphere": ""
  },
  "cinematography": {
    "shot_type": "",
    "framing": "",
    "camera_position": "",
    "camera_height": "",
    "camera_angle": "",
    "perspective": "",
    "lens": "",
    "focal_length": "",
    "depth_of_field": "",
    "focus_subject": "",
    "focus_behavior": "",
    "camera_movement": "",
    "camera_speed": "",
    "camera_stability": "",
    "parallax": "",
    "composition": "",
    "headroom": "",
    "lead_room": ""
  },
  "motion": {
    "subject_motion": "",
    "camera_motion": "",
    "environment_motion": "",
    "secondary_motion": "",
    "wind": "",
    "cloth_motion": "",
    "hair_motion": "",
    "particle_motion": "",
    "physics": "",
    "motion_intensity": ""
  },
  "lighting": {
    "lighting_style": "",
    "key_light": "",
    "fill_light": "",
    "rim_light": "",
    "practical_lights": "",
    "light_direction": "",
    "light_quality": "",
    "light_color": "",
    "shadow_behavior": "",
    "contrast": "",
    "exposure": "",
    "specular_behavior": ""
  },
  "visual_style": {
    "medium": "",
    "style": "",
    "genre": "",
    "era": "",
    "realism_level": "",
    "visual_reference": "",
    "film_emulation": "",
    "texture": "",
    "grain": "",
    "color_palette": "",
    "color_grading": "",
    "contrast_style": "",
    "art_direction": "",
    "finish": ""
  },
  "audio": {
    "dialogue": [],
    "voice_characteristics": "",
    "ambient_sound": "",
    "sound_effects": [],
    "foley": "",
    "music": "",
    "music_timing": "",
    "audio_mood": "",
    "audio_perspective": ""
  },
  "dialogue": {
    "speaker": "",
    "line": "",
    "delivery": "",
    "emotion": "",
    "volume": "",
    "pace": "",
    "accent": "",
    "lip_sync": True
  },
  "timing": {
    "beats": [
      {
        "time": "0-2s",
        "event": ""
      },
      {
        "time": "2-5s",
        "event": ""
      },
      {
        "time": "5-8s",
        "event": ""
      }
    ]
  },
  "transitions": {
    "opening": "",
    "ending": "",
    "transition_type": "",
    "continuity": "",
    "cut_behavior": ""
  },
  "text": {
    "enabled": False,
    "content": "",
    "placement": "",
    "typography": "",
    "font_style": "",
    "size": "",
    "color": "",
    "animation": ""
  },
  "references": {
    "character_reference": [],
    "product_reference": [],
    "environment_reference": [],
    "style_reference": [],
    "voice_reference": [],
    "reference_usage": ""
  },
  "frames": {
    "first_frame": "",
    "last_frame": "",
    "transition_instruction": ""
  },
  "continuity": {
    "character_consistency": "",
    "wardrobe_consistency": "",
    "prop_consistency": "",
    "environment_consistency": "",
    "lighting_consistency": "",
    "camera_consistency": "",
    "color_consistency": ""
  },
  "constraints": {
    "must_include": [],
    "must_not_change": [],
    "avoid": [],
    "negative_guidance": [],
    "realism_constraints": [],
    "physics_constraints": []
  },
  "quality_control": {
    "priority_1": "",
    "priority_2": "",
    "priority_3": "",
    "failure_conditions": []
  }
}

IMAGE_PROMPT_TEMPLATE = {
  "project": {
    "title": "",
    "purpose": "",
    "asset_type": "",
    "aspect_ratio": "9:16",
    "resolution": "4K"
  },
  "concept": {
    "core_idea": "",
    "story": "",
    "visual_message": "",
    "emotion": "",
    "mood": ""
  },
  "subject": {
    "primary_subject": "",
    "secondary_subjects": [],
    "subject_count": 1,
    "age": "",
    "gender_presentation": "",
    "ethnicity_or_cultural_context": "",
    "face": "",
    "hair": "",
    "skin": "",
    "body_type": "",
    "wardrobe": "",
    "accessories": "",
    "distinctive_features": "",
    "pose": "",
    "expression": "",
    "gaze_direction": "",
    "action": "",
    "interaction": ""
  },
  "environment": {
    "location": "",
    "specific_place": "",
    "setting": "",
    "background": "",
    "foreground": "",
    "midground": "",
    "architecture": "",
    "terrain": "",
    "surfaces": "",
    "materials": "",
    "props": [],
    "environmental_details": "",
    "time_of_day": "",
    "season": "",
    "weather": "",
    "atmosphere": ""
  },
  "composition": {
    "shot_type": "",
    "framing": "",
    "camera_angle": "",
    "camera_height": "",
    "perspective": "",
    "viewpoint": "",
    "subject_placement": "",
    "symmetry": "",
    "negative_space": "",
    "foreground_layer": "",
    "midground_layer": "",
    "background_layer": "",
    "visual_hierarchy": "",
    "leading_lines": "",
    "balance": "",
    "crop": ""
  },
  "camera": {
    "camera_type": "",
    "lens": "",
    "focal_length": "",
    "aperture": "",
    "depth_of_field": "",
    "focus": "",
    "focus_behavior": "",
    "perspective_distortion": "",
    "image_character": ""
  },
  "lighting": {
    "lighting_style": "",
    "key_light": "",
    "fill_light": "",
    "rim_light": "",
    "practical_lights": "",
    "light_direction": "",
    "light_source": "",
    "light_quality": "",
    "light_color": "",
    "shadow_behavior": "",
    "contrast": "",
    "exposure": "",
    "specular_behavior": ""
  },
  "visual_style": {
    "medium": "",
    "style": "",
    "genre": "",
    "era": "",
    "realism_level": "",
    "visual_reference": "",
    "film_emulation": "",
    "texture": "",
    "grain": "",
    "color_palette": "",
    "color_grading": "",
    "contrast_style": "",
    "art_direction": "",
    "finish": ""
  },
  "materials_and_surface_detail": {
    "skin_texture": "",
    "fabric_texture": "",
    "metal_texture": "",
    "glass_behavior": "",
    "wood_texture": "",
    "stone_texture": "",
    "water_behavior": "",
    "reflection_behavior": "",
    "weathering": "",
    "imperfections": ""
  },
  "physics_and_realism": {
    "gravity": "",
    "shadow_accuracy": "",
    "reflection_accuracy": "",
    "scale_accuracy": "",
    "anatomical_accuracy": "",
    "material_accuracy": "",
    "historical_accuracy": ""
  },
  "text": {
    "enabled": False,
    "content": "",
    "exact_wording": "",
    "placement": "",
    "typography": "",
    "font_style": "",
    "font_weight": "",
    "font_size": "",
    "color": "",
    "alignment": "",
    "line_breaks": "",
    "text_effect": "",
    "language": ""
  },
  "references": {
    "character_reference": [],
    "object_reference": [],
    "environment_reference": [],
    "style_reference": [],
    "composition_reference": [],
    "reference_roles": ""
  },
  "continuity": {
    "character_identity": "",
    "wardrobe": "",
    "object_identity": "",
    "environment": "",
    "lighting": "",
    "color": "",
    "style": ""
  },
  "constraints": {
    "must_include": [],
    "must_not_change": [],
    "avoid": [],
    "negative_guidance": [],
    "accuracy_requirements": [],
    "design_requirements": []
  },
  "quality_control": {
    "priority_1": "",
    "priority_2": "",
    "priority_3": "",
    "failure_conditions": []
  }
}