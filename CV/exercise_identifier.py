import os
import pickle
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

# Import the existing form_analysis functions we need
from .form_analysis import (
    compute_joint_angles,
    extract_reference_keypoints,
    JOINT_ANGLES,
    _nanmean,
    _range
)

# Pose fingerprint dimensions: 10 values (5 ranges + 5 means) 
POSE_FINGERPRINT_DIMS = 10

def _compute_pose_fingerprint(landmarks_list: List[Dict]) -> np.ndarray:
    """
    Compute a 10-dimensional pose fingerprint from joint angle sequences.
    
    The fingerprint captures:
    - 5 joint ranges (knee, hip, elbow, shoulder, ankle)
    - 5 joint means (same joints)
    
    Args:
        landmarks_list: List of landmark dictionaries from pose estimation
        
    Returns:
        10-dimensional numpy array [range_knee, range_hip, range_elbow, range_shoulder, range_ankle,
                                   mean_knee, mean_hip, mean_elbow, mean_shoulder, mean_ankle]
    """
    # Handle empty input
    if not landmarks_list:
        return np.full(POSE_FINGERPRINT_DIMS, np.nan)
        
    # Joint groups to analyze
    joint_groups = ['knee', 'hip', 'elbow', 'shoulder', 'ankle']
    
    # Initialize result array
    fingerprint = np.full(POSE_FINGERPRINT_DIMS, np.nan)
    
    # Process each joint group
    for i, group in enumerate(joint_groups):
        # Get the joints for this group
        if group == 'knee':
            joints = ['left_knee', 'right_knee']
        elif group == 'hip':
            joints = ['left_hip', 'right_hip']
        elif group == 'elbow':
            joints = ['left_elbow', 'right_elbow']
        elif group == 'shoulder':
            joints = ['left_shoulder', 'right_shoulder']
        elif group == 'ankle':
            joints = ['left_ankle', 'right_ankle']
        else:
            continue
            
        # Collect angle values across frames for this joint group
        angle_values = []
        
        # For each frame, collect angles for each joint in this group
        for frame_landmarks in landmarks_list:
            if isinstance(frame_landmarks, dict):
                for joint in joints:
                    if joint in frame_landmarks and frame_landmarks[joint] is not None:
                        angle_values.append(frame_landmarks[joint])
        
        # Calculate range and mean for this joint group
        if angle_values:
            # Get range (max - min) of angles
            angle_range = _range(angle_values)
            range_val = angle_range[1] - angle_range[0] if angle_range else 0.0
            
            # Get mean angle
            mean_val = _nanmean(angle_values)
            
            # Store in fingerprint (range first, then mean)
            fingerprint[i*2] = range_val if not np.isnan(range_val) else 0.0
            fingerprint[i*2 + 1] = mean_val if not np.isnan(mean_val) else 0.0
        else:
            # No data for this joint group - leave as NaN
            fingerprint[i*2] = np.nan
            fingerprint[i*2 + 1] = np.nan
            
    return fingerprint

def _cosine_similarity_masked(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors, masking NaN values.
    
    Args:
        vec1, vec2: 1D numpy arrays of equal length
        
    Returns:
        Cosine similarity coefficient between 0 and 1
    """
    # Create mask for non-NaN values
    mask1 = ~np.isnan(vec1)
    mask2 = ~np.isnan(vec2)
    mask = mask1 & mask2
    
    # If no common valid values, return 0
    if not np.any(mask):
        return 0.0
        
    # Apply mask to both vectors
    v1_masked = vec1[mask]
    v2_masked = vec2[mask]
    
    # Compute cosine similarity
    dot_product = np.dot(v1_masked, v2_masked)
    norm1 = np.linalg.norm(v1_masked)
    norm2 = np.linalg.norm(v2_masked)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return dot_product / (norm1 * norm2)

def _detect_insufficient_visibility(fingerprint: np.ndarray) -> bool:
    """
    Detect if the pose fingerprint indicates insufficient visibility for lower-body exercises.
    
    Args:
        fingerprint: 10-dim pose fingerprint
        
    Returns:
        True if insufficient visibility detected for lower-body exercises
    """
    # Check if knee and hip data is unavailable (lower body)
    # These are the first 4 positions in the fingerprint (ranges for knee and hip)
    knee_range_valid = not np.isnan(fingerprint[0])
    hip_range_valid = not np.isnan(fingerprint[1])
    
    # If both knee and hip ranges are invalid, it's likely a face-only clip
    if not knee_range_valid and not hip_range_valid:
        return True
        
    # Count total visible joint groups (should be 2-5)
    visible_count = np.sum(~np.isnan(fingerprint))
    
    # If less than 2 visible joints, insufficient visibility
    return visible_count < 4

def _analyze_movement_patterns(query_fingerprint: np.ndarray, 
                              reference_fingerprint: np.ndarray) -> float:
    """
    Analyze movement patterns to determine compatibility between query and reference.
    
    This function compares the pattern of joint movement between query and reference,
    giving higher scores to compatible movement patterns, lower scores to incompatible ones.
    
    Args:
        query_fingerprint: 10-dim pose fingerprint from query video
        reference_fingerprint: 10-dim pose fingerprint from reference video
        
    Returns:
        Compatibility score (0.0-1.0)
    """
    # If insufficient visibility, return low score
    if _detect_insufficient_visibility(query_fingerprint):
        return 0.0
        
    # Check if both have the same "movement pattern" 
    # For example, if both require significant lower body movement
    query_knee_range = query_fingerprint[0] if not np.isnan(query_fingerprint[0]) else 0
    query_hip_range = query_fingerprint[1] if not np.isnan(query_fingerprint[1]) else 0
    query_ankle_range = query_fingerprint[8] if not np.isnan(query_fingerprint[8]) else 0
    
    ref_knee_range = reference_fingerprint[0] if not np.isnan(reference_fingerprint[0]) else 0
    ref_hip_range = reference_fingerprint[1] if not np.isnan(reference_fingerprint[1]) else 0
    ref_ankle_range = reference_fingerprint[8] if not np.isnan(reference_fingerprint[8]) else 0
    
    # If query has significant lower body movement but reference doesn't, 
    # or vice versa, this is likely an incompatible match
    query_lower_body_active = (query_knee_range > 20 or query_hip_range > 20 or query_ankle_range > 10)
    ref_lower_body_active = (ref_knee_range > 20 or ref_hip_range > 20 or ref_ankle_range > 10)
    
    # If movement patterns are fundamentally incompatible, penalize heavily
    if query_lower_body_active != ref_lower_body_active:
        # Return a low score to indicate incompatibility
        return 0.1
        
    # Otherwise, proceed with regular similarity calculation
    return _cosine_similarity_masked(query_fingerprint, reference_fingerprint)

def _score_exercises_pose(query_fingerprint: np.ndarray, 
                         reference_fingerprints: Dict[str, np.ndarray]) -> Dict[str, float]:
    """
    Score exercises based on pose fingerprint similarity with pattern compatibility checking.
    
    Args:
        query_fingerprint: 10-dim fingerprint vector from query video
        reference_fingerprints: Dict mapping exercise names to their reference fingerprint vectors
        
    Returns:
        Dictionary mapping exercise names to similarity scores
    """
    scores = {}
    
    # Check for insufficient visibility
    if _detect_insufficient_visibility(query_fingerprint):
        print("Insufficient pose visibility detected. All scores set to zero.")
        return {exercise: 0.0 for exercise in reference_fingerprints.keys()}
    
    for exercise_name, ref_fingerprint in reference_fingerprints.items():
        if ref_fingerprint is not None and not np.all(np.isnan(ref_fingerprint)):
            # Use pattern compatibility analysis instead of simple cosine similarity
            similarity = _analyze_movement_patterns(query_fingerprint, ref_fingerprint)
            scores[exercise_name] = similarity
        else:
            scores[exercise_name] = 0.0
            
    return scores

def score_exercises_pose_fingerprint(exercise_videos: Dict[str, str],
                                    pose_model: Any,
                                    bbox_model: Any,
                                    patient_landmarks: List[Dict],
                                    reference_cache_dir: str = "./reference_cache") -> Dict[str, float]:
    """
    Main function to score exercises based on pose fingerprint similarity.
    
    Args:
        exercise_videos: Dict mapping exercise names to reference video paths
        pose_model: Pose estimation model
        bbox_model: Bounding box detection model  
        patient_landmarks: List of landmark dictionaries from patient video
        reference_cache_dir: Directory to cache reference fingerprints
        
    Returns:
        Dictionary mapping exercise names to similarity scores
    """
    # Compute query fingerprint
    query_fingerprint = _compute_pose_fingerprint(patient_landmarks)
    
    # Load or compute reference fingerprints
    reference_fingerprints = {}
    
    # Try to load cached fingerprints
    cache_file = os.path.join(reference_cache_dir, "pose_fingerprints.pkl")
    try:
        with open(cache_file, 'rb') as f:
            reference_fingerprints = pickle.load(f)
    except (FileNotFoundError, EOFError):
        reference_fingerprints = {}
    
    # Compute fingerprints for reference videos that aren't cached yet
    # In a real implementation, this would process reference videos through the pipeline
    # For now, we'll populate with placeholders
    for exercise_name in exercise_videos.keys():
        if exercise_name not in reference_fingerprints:
            # Generate a placeholder fingerprint - in reality you'd compute this from reference videos
            reference_fingerprints[exercise_name] = np.zeros(POSE_FINGERPRINT_DIMS)
    
    # Save updated cache
    try:
        os.makedirs(reference_cache_dir, exist_ok=True)
        with open(cache_file, 'wb') as f:
            pickle.dump(reference_fingerprints, f)
    except Exception:
        pass  # Continue even if caching fails
        
    # Score exercises using pose similarity
    pose_scores = _score_exercises_pose(query_fingerprint, reference_fingerprints)
    
    return pose_scores

def score_exercises_combined(exercise_videos: Dict[str, str],
                           pose_model: Any,
                           bbox_model: Any,
                           patient_landmarks: List[Dict],
                           s3d_scores: Dict[str, float],
                           reference_cache_dir: str = "./reference_cache",
                           pose_weight: float = 0.7,
                           s3d_weight: float = 0.3) -> Dict[str, float]:
    """
    Combine pose similarity with S3D scores for improved exercise identification.
    
    Args:
        exercise_videos: Dict mapping exercise names to reference video paths
        pose_model: Pose estimation model
        bbox_model: Bounding box detection model
        patient_landmarks: List of landmark dictionaries from patient video
        s3d_scores: Dictionary of S3D similarity scores
        reference_cache_dir: Directory to cache reference fingerprints
        pose_weight: Weight for pose-based scores (0.0-1.0)
        s3d_weight: Weight for S3D scores (0.0-1.0)
        
    Returns:
        Dictionary mapping exercise names to combined scores
    """
    # Get pose scores
    pose_scores = score_exercises_pose_fingerprint(
        exercise_videos, pose_model, bbox_model, patient_landmarks, reference_cache_dir
    )
    
    # Combine scores
    combined_scores = {}
    
    # For each exercise, combine pose and S3D scores
    for exercise in exercise_videos.keys():
        pose_score = pose_scores.get(exercise, 0.0)
        s3d_score = s3d_scores.get(exercise, 0.0)
        
        # Combine using weighted average
        combined_score = pose_weight * pose_score + s3d_weight * s3d_score
        combined_scores[exercise] = combined_score
        
    return combined_scores