import math
import heapq
import time
from CommunityScorer import CommunityScorer

class BitVectorCommunityDetector:
    """
    Community detection with bitvector optimization for keywords and dual pruning strategies.
    
    Features:
    - Bitvector representation of keywords for space optimization
    - Radius-based community detection (r=1 or r=2)
    - Dual pruning strategies: keyword-based and score-based
    - Option to precompute r-radius subgraphs
    """
    
    def __init__(self, social_network, road_network):
        """
        Initialize the community detector
        
        Args:
            social_network: SocialNetwork object
            road_network: RoadNetwork object
        """
        self.social_network = social_network
        self.road_network = road_network
        self.scorer = CommunityScorer()
        
        # Bitvector system
        self.keyword_map = {}  # Maps keyword ID to bit position
        self.reverse_map = {}  # Maps bit position to keyword ID
        self.next_position = 0  # Next available bit position
        
        # Cache for user keyword bitvectors
        self.user_keyword_bitvectors = {}
        
        # Cache for precomputed r-radius subgraphs
        self.radius1_subgraphs = {}  # User -> {users, bitvector}
        self.radius2_subgraphs = {}  # User -> {users, bitvector}
        
        # Flag to indicate if precomputation is done
        self.radius1_precomputed = False
        self.radius2_precomputed = False
    
    #--------------------------
    # Bitvector functionality
    #--------------------------
    
    def get_bit_position(self, keyword_id):
        """
        Get or create bit position for a keyword
        
        Args:
            keyword_id: ID of the keyword
            
        Returns:
            int: Bit position for the keyword
        """
        if keyword_id not in self.keyword_map:
            position = self.next_position
            self.keyword_map[keyword_id] = position
            self.reverse_map[position] = keyword_id
            self.next_position += 1
            return position
        
        return self.keyword_map[keyword_id]
    
    def keywords_to_bitvector(self, keywords):
        """
        Convert a list of keywords to a bitvector
        
        Args:
            keywords: List of keyword IDs
            
        Returns:
            int: Bitvector representation of keywords
        """
        bitvector = 0
        
        for keyword in keywords:
            position = self.get_bit_position(keyword)
            bitvector |= (1 << position)
            
        return bitvector
    
    def bitvector_to_keywords(self, bitvector):
        """
        Convert a bitvector back to a list of keywords
        
        Args:
            bitvector: Integer bitvector representation
            
        Returns:
            list: List of keyword IDs
        """
        keywords = []
        
        for position in range(self.next_position):
            if bitvector & (1 << position):
                keywords.append(self.reverse_map[position])
                
        return keywords
    
    def has_all_keywords(self, bitvector, query_bitvector):
        """
        Check if a bitvector contains all keywords in a query bitvector
        
        Args:
            bitvector: Bitvector to check
            query_bitvector: Query bitvector with required keywords
            
        Returns:
            bool: True if bitvector contains all query keywords
        """
        return (bitvector & query_bitvector) == query_bitvector
    
    def get_user_keyword_bitvector(self, user_id):
        """
        Get the bitvector representation of a user's keywords
        Uses caching for efficiency
        
        Args:
            user_id: User ID
            
        Returns:
            int: Bitvector representation of user's keywords
        """
        if user_id in self.user_keyword_bitvectors:
            return self.user_keyword_bitvectors[user_id]
        
        try:
            keywords = self.social_network.getUserKeywords(user_id)
            bitvector = self.keywords_to_bitvector(keywords)
            self.user_keyword_bitvectors[user_id] = bitvector
            return bitvector
        except:
            # Return empty bitvector if user has no keywords
            return 0
    
    #--------------------------
    # Subgraph computation
    #--------------------------
    
    def compute_radius_subgraph(self, center_user, radius):
        """
        Compute r-radius subgraph for a user
        
        Args:
            center_user: User ID at the center of subgraph
            radius: Radius (number of hops)
            
        Returns:
            tuple: (users, keyword_bitvector)
                users is a dict mapping user_id to hop distance
                keyword_bitvector is the combined bitvector of all keywords in the subgraph
        """
        # BFS to get r-radius subgraph
        subgraph = {center_user: 0}  # User -> hop distance
        visited = {center_user}
        queue = [(center_user, 0)]  # (user, hop_distance)
        
        # Start with center user's keywords
        combined_bitvector = self.get_user_keyword_bitvector(center_user)
        
        while queue:
            user, hop_distance = queue.pop(0)
            
            # Stop if we've reached the radius
            if hop_distance >= radius:
                continue
            
            # Get user's relationships
            try:
                relationships = self.social_network.getUserRel(user)
                for rel in relationships:
                    if not rel:
                        continue
                    
                    related_user = rel[0]
                    if related_user not in visited:
                        visited.add(related_user)
                        subgraph[related_user] = hop_distance + 1
                        queue.append((related_user, hop_distance + 1))
                        
                        # Add keywords from this user to combined bitvector
                        user_bitvector = self.get_user_keyword_bitvector(related_user)
                        combined_bitvector |= user_bitvector
            except:
                # Skip if we can't get relationships
                pass
        
        return subgraph, combined_bitvector
    
    def precompute_radius_subgraphs(self, radius=2, max_users=None, verbose=True):
        """
        Precompute r-radius subgraphs for all users or a subset
        
        Args:
            radius: Radius to precompute (1 or 2)
            max_users: Maximum number of users to precompute (None for all)
            verbose: Whether to print progress
        """
        if verbose:
            print(f"Precomputing r={radius} subgraphs...")
            start_time = time.time()
        
        # Get all users or a subset
        all_users = self.social_network.getUsers()
        if max_users is not None:
            all_users = all_users[:min(max_users, len(all_users))]
        
        total_users = len(all_users)
        
        # Initialize progress tracking
        if verbose:
            progress_interval = max(1, total_users // 10)
        
        for i, user in enumerate(all_users):
            # Show progress
            if verbose and i % progress_interval == 0:
                print(f"Progress: {i}/{total_users} users processed ({i/total_users*100:.1f}%)")
            
            # Compute r-radius subgraph
            subgraph, bitvector = self.compute_radius_subgraph(user, radius)
            
            # Store in appropriate cache
            if radius == 1:
                self.radius1_subgraphs[user] = {
                    'subgraph': subgraph,
                    'bitvector': bitvector
                }
            else:
                self.radius2_subgraphs[user] = {
                    'subgraph': subgraph,
                    'bitvector': bitvector
                }
        
        # Mark as precomputed
        if radius == 1:
            self.radius1_precomputed = True
        else:
            self.radius2_precomputed = True
        
        if verbose:
            elapsed = time.time() - start_time
            print(f"Precomputation complete! Processed {total_users} users in {elapsed:.2f} seconds")
    
    #--------------------------
    # Community detection
    #--------------------------
    
    def find_top_k_communities(self, query_keywords, k=5, radius=2, min_similarity=0.01, use_precomputation=True):
        """
        Find top-k communities with dual pruning strategies
        
        Args:
            query_keywords: List of keyword IDs in the query
            k: Number of top communities to return
            radius: Radius parameter (1 or 2)
            min_similarity: Minimum similarity threshold
            use_precomputation: Whether to use precomputed subgraphs if available
            
        Returns:
            list: Top-k communities with scores
        """
        # Validate parameters
        if radius not in [1, 2]:
            print(f"Warning: Radius {radius} not supported. Using radius=2 instead.")
            radius = 2
        
        # Convert query keywords to bitvector
        query_bitvector = self.keywords_to_bitvector(query_keywords)
        
        # Get all users
        users = self.social_network.getUsers()
        
        # Check if we have precomputed subgraphs
        use_precomp = use_precomputation and (
            (radius == 1 and self.radius1_precomputed) or 
            (radius == 2 and self.radius2_precomputed)
        )
        
        if not use_precomp:
            print("Using on-demand computation (precomputed data not available or disabled).")
        
        # Initialize min-heap for top-k tracking (negative scores for max-heap behavior)
        # Using tuples of (score, user_id) for the heap
        top_k_heap = []
        min_top_k_score = 0  # Keeps track of minimum score in top-k
        
        # Candidate communities
        communities = []
        
        # Process each user as potential community center
        for user in users:
            # Skip if we can't get data for this user
            try:
                # PRUNING STRATEGY 1: Keyword-based pruning
                # Skip users whose r-radius subgraph doesn't contain all query keywords
                
                if radius == 1 and use_precomp and user in self.radius1_subgraphs:
                    # Use precomputed r=1 subgraph
                    subgraph = self.radius1_subgraphs[user]['subgraph']
                    subgraph_bitvector = self.radius1_subgraphs[user]['bitvector']
                elif radius == 2 and use_precomp and user in self.radius2_subgraphs:
                    # Use precomputed r=2 subgraph
                    subgraph = self.radius2_subgraphs[user]['subgraph']
                    subgraph_bitvector = self.radius2_subgraphs[user]['bitvector']
                else:
                    # Compute on-demand
                    subgraph, subgraph_bitvector = self.compute_radius_subgraph(user, radius)
                
                # Check if subgraph has all query keywords
                if not self.has_all_keywords(subgraph_bitvector, query_bitvector):
                    continue
                
                # Extract community from subgraph
                community_users = list(subgraph.keys())
                
                # Skip if community is too small
                if len(community_users) < 3:
                    continue
                
                # Score the community
                score, components = self.scorer.calculate_community_score(
                    community_users, 
                    self.social_network, 
                    self.road_network
                )
                
                # PRUNING STRATEGY 2: Score-based pruning
                # Skip if score is below the minimum top-k score (when we have k communities)
                if len(top_k_heap) >= k and score <= min_top_k_score:
                    continue
                
                # Create community object
                community = {
                    'center': user,
                    'users': community_users,
                    'score': score,
                    'components': components,
                    'size': len(community_users),
                    'subgraph': subgraph  # Store hop distances for visualization
                }
                
                # Update top-k heap
                if len(top_k_heap) < k:
                    # Heap not full yet, add new community
                    heapq.heappush(top_k_heap, (score, user))
                    communities.append(community)
                    
                    # Update min score if heap is now full
                    if len(top_k_heap) == k:
                        min_top_k_score = min([s for s, _ in top_k_heap])
                else:
                    # Heap is full, replace minimum if new score is higher
                    heapq.heappushpop(top_k_heap, (score, user))
                    communities.append(community)
                    
                    # Update min score
                    min_top_k_score = min([s for s, _ in top_k_heap])
                
            except Exception as e:
                # Skip on error
                continue
        
        # Sort communities by score (descending)
        communities.sort(key=lambda x: x['score'], reverse=True)
        
        # Return top-k communities
        return communities[:k]
    
    def create_community_tree(self, center_user, query_keywords, radius=2, use_precomputation=True):
        """
        Create a tree representation of community for GUI visualization
        
        Args:
            center_user: Center user ID
            query_keywords: List of keyword IDs
            radius: Maximum radius
            use_precomputation: Whether to use precomputed subgraphs if available
            
        Returns:
            dict: Tree structure for visualization
        """
        # Convert query keywords to bitvector
        query_bitvector = self.keywords_to_bitvector(query_keywords)
        
        # Check if we have precomputed subgraphs
        use_precomp = use_precomputation and (
            (radius == 1 and self.radius1_precomputed) or 
            (radius == 2 and self.radius2_precomputed)
        )
        
        # Compute or get subgraph
        if radius == 1 and use_precomp and center_user in self.radius1_subgraphs:
            subgraph = self.radius1_subgraphs[center_user]['subgraph']
        elif radius == 2 and use_precomp and center_user in self.radius2_subgraphs:
            subgraph = self.radius2_subgraphs[center_user]['subgraph']
        else:
            subgraph, _ = self.compute_radius_subgraph(center_user, radius)
        
        # Build tree recursively
        return self._build_community_tree(center_user, subgraph, query_bitvector)
    
    def _build_community_tree(self, user, subgraph, query_bitvector, visited=None):
        """
        Recursively build community tree
        
        Args:
            user: Current user
            subgraph: r-radius subgraph
            query_bitvector: Query keyword bitvector
            visited: Set of visited users
        """
        if visited is None:
            visited = set()
        
        visited.add(user)
        
        # Get user's keyword bitvector
        user_bitvector = self.get_user_keyword_bitvector(user)
        
        # Check if user has all query keywords
        has_all_keywords = self.has_all_keywords(user_bitvector, query_bitvector)
        
        # Calculate similarity with query
        jaccard_similarity = self._calculate_jaccard_similarity(user_bitvector, query_bitvector)
        
        # Node data (compatible with existing GUI code)
        node = {
            'user': user,
            'distance': subgraph.get(user, 0),
            'keyword_score': jaccard_similarity,
            'rel_score': 0.0,  # Will be calculated separately
            'deg_sim': jaccard_similarity,  # Using keyword similarity as degree similarity
            'satisfy': has_all_keywords,
            'keywords': self.bitvector_to_keywords(user_bitvector),
            'hops': subgraph.get(user, 0),
            'children': {}
        }
        
        # Add children
        try:
            relationships = self.social_network.getUserRel(user)
            for rel in relationships:
                if not rel:
                    continue
                
                related_user = rel[0]
                if related_user in subgraph and related_user not in visited:
                    # Only add users in the subgraph and not visited yet
                    node['children'][related_user] = self._build_community_tree(
                        related_user, subgraph, query_bitvector, visited
                    )
        except:
            pass
        
        return node
    
    def _calculate_jaccard_similarity(self, bitvector1, bitvector2):
        """
        Calculate Jaccard similarity between two bitvectors
        
        Args:
            bitvector1: First bitvector
            bitvector2: Second bitvector
            
        Returns:
            float: Jaccard similarity [0,1]
        """
        if bitvector1 == 0 and bitvector2 == 0:
            return 0.0
            
        # Count bits in intersection
        intersection = bitvector1 & bitvector2
        intersection_count = bin(intersection).count('1')
        
        # Count bits in union
        union = bitvector1 | bitvector2
        union_count = bin(union).count('1')
        
        # Calculate Jaccard similarity
        return intersection_count / max(1, union_count)


# Example usage:
def example_usage():
    """Example of how to use the BitVectorCommunityDetector"""
    # Create or load your social and road networks
    social_network = None  # Replace with your SocialNetwork instance
    road_network = None    # Replace with your RoadNetwork instance
    
    # Create detector
    detector = BitVectorCommunityDetector(social_network, road_network)
    
    # Optional: Precompute r-radius subgraphs for faster queries
    detector.precompute_radius_subgraphs(radius=1)
    detector.precompute_radius_subgraphs(radius=2)
    
    # Find top-k communities
    query_keywords = ["coffee", "travel", "food"]
    communities = detector.find_top_k_communities(
        query_keywords,
        k=5,                   # Number of communities to return
        radius=2,              # Radius parameter (1 or 2)
        min_similarity=0.01,   # Minimum similarity threshold
        use_precomputation=True  # Use precomputed subgraphs if available
    )
    
    # Print results
    for i, community in enumerate(communities):
        print(f"Community {i+1}:")
        print(f"  Center: {community['center']}")
        print(f"  Size: {community['size']} users")
        print(f"  Score: {community['score']:.4f}")
        print(f"  Components:")
        print(f"    Keywords: {community['components']['keywords']:.4f}")
        print(f"    Distance: {community['components']['distance']:.4f}")
        print(f"    Connections: {community['components']['connections']:.4f}")
        print()