"""
This file bridges the existing community search functionality with the new BitVector implementation.
Add this to your project alongside BitVectorCommunityDetector.py and CommunityScorer.py.
"""

class CommunityBridge:
    """
    Bridge class to connect the original community search functionality 
    with the new BitVector implementation.
    """
    
    def __init__(self, gui_instance):
        """
        Initialize with reference to the GUI instance for access to networks and methods
        
        Args:
            gui_instance: The GUI instance
        """
        self.gui = gui_instance
        
        # Initialize detector if networks are already available
        if self.gui.selectedSocialNetwork and self.gui.selectedRoadNetwork:
            self.ensure_detector_exists()
    
    def ensure_detector_exists(self):
        """Make sure the BitVector detector is created if needed"""
        if not hasattr(self.gui, 'communityDetector') or not self.gui.communityDetector:
            self.gui.initializeCommunityDetector()
    
    def process_community_query(self, query_user, query_keywords, min_keywords, radius, min_similarity):
        """
        Process a community query using the BitVector implementation
        
        Args:
            query_user: Query user ID
            query_keywords: List of keywords for the query
            min_keywords: Minimum number of keywords (k parameter) 
            radius: Radius parameter (r)
            min_similarity: Minimum similarity threshold
            
        Returns:
            Community tree structure or None if no results
        """
        # Make sure detector exists
        self.ensure_detector_exists()
        
        # Convert parameters to expected types
        try:
            min_keywords = float(min_keywords)
            radius = float(radius)
            min_similarity = float(min_similarity)
        except ValueError:
            print("Error converting parameters to expected types")
            return None
        
        # Cap radius to 1 or 2 (supported values)
        radius = min(2, max(1, radius))
        
        # Get communities using BitVector implementation
        communities = self.gui.communityDetector.find_top_k_communities(
            query_keywords,
            k=5,  # Default to top 5 communities
            radius=int(radius),
            min_similarity=min_similarity,
            use_precomputation=hasattr(self.gui, 'precomputed') and self.gui.precomputed
        )
        
        if not communities:
            return None
        
        # Get the top community
        top_community = communities[0]
        
        # Convert to tree structure expected by original code
        # This creates a compatible tree structure for visualization with existing code
        tree = self.gui.communityDetector.create_community_tree(
            top_community['center'], 
            query_keywords, 
            radius=int(radius)
        )
        
        # Store the communities for later access
        self.gui.current_communities = communities
        
        return tree