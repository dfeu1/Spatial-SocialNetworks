import math

class CommunityScorer:
    """
    Calculate scores for communities based on keywords (40%), distance (30%), and connections (30%).
    S(C) = 0.4⋅K(C) + 0.3⋅D(C) + 0.3⋅Conn(C)
    """
    
    def calculate_community_score(self, community, social_network, road_network):
        """
        Calculate a score for a community based on keywords (40%), distance (30%), and connections (30%).
        
        Args:
            community (list): List of user IDs in the community
            social_network (SocialNetwork): The social network object containing user data
            road_network (RoadNetwork): The road network object for distance calculations
            
        Returns:
            float: Overall community score between 0 and 1
            dict: Individual component scores (keywords, distance, connections)
        """
        if not community or len(community) < 2:
            return 0, {'keywords': 0, 'distance': 0, 'connections': 0}
            
        # Calculate keyword similarity score (40%)
        keyword_score = self.calculate_keyword_similarity(community, social_network)
        
        # Calculate physical distance score (30%)
        distance_score = self.calculate_distance_score(community, social_network, road_network)
        
        # Calculate social connection score (30%)
        connection_score = self.calculate_connection_score(community, social_network)
        
        # Calculate overall score with weights
        overall_score = 0.4 * keyword_score + 0.3 * distance_score + 0.3 * connection_score
        
        component_scores = {
            'keywords': keyword_score,
            'distance': distance_score,
            'connections': connection_score
        }
        
        return overall_score, component_scores
        
    def calculate_keyword_similarity(self, community, social_network):
        """
        Calculate the keyword similarity score for a community.
        
        Higher score means users share more common interests/keywords.
        
        Args:
            community (list): List of user IDs in the community
            social_network (SocialNetwork): The social network object containing user data
            
        Returns:
            float: Score between 0 and 1 indicating keyword similarity
        """
        # Get all keywords for each user in the community
        user_keywords = {}
        all_keywords = set()
        
        for user_id in community:
            keywords = social_network.getUserKeywords(user_id)
            user_keywords[user_id] = set(keywords)
            all_keywords.update(keywords)
        
        if not all_keywords:
            return 0
            
        # Calculate Jaccard similarity between each pair of users
        total_similarity = 0
        pair_count = 0
        
        for i, user1 in enumerate(community):
            for j in range(i+1, len(community)):
                user2 = community[j]
                
                # Jaccard similarity: size of intersection / size of union
                intersection = len(user_keywords[user1] & user_keywords[user2])
                union = len(user_keywords[user1] | user_keywords[user2])
                
                if union > 0:
                    similarity = intersection / union
                    total_similarity += similarity
                    pair_count += 1
        
        # Return average similarity across all pairs
        return total_similarity / max(1, pair_count)

    def calculate_distance_score(self, community, social_network, road_network):
        """
        Calculate the physical distance score for a community.
        
        Lower distances result in higher scores.
        
        Args:
            community (list): List of user IDs in the community
            social_network (SocialNetwork): The social network object containing user location data
            road_network (RoadNetwork): The road network object for distance calculations
            
        Returns:
            float: Score between 0 and 1 indicating physical proximity
        """
        # Get user locations
        user_locations = {}
        for user_id in community:
            loc = social_network.userLoc(user_id)
            if loc:
                user_locations[user_id] = (float(loc[0][0]), float(loc[0][1]))
        
        if len(user_locations) < 2:
            return 0
        
        # Calculate average distance between all pairs of users
        total_distance = 0
        pair_count = 0
        max_distance = 0
        
        for i, user1 in enumerate(list(user_locations.keys())):
            user1_loc = user_locations[user1]
            
            for j, user2 in enumerate(list(user_locations.keys())[i+1:], i+1):
                user2_loc = user_locations[user2]
                
                # Calculate Euclidean distance
                distance = ((user1_loc[0] - user2_loc[0])**2 + (user1_loc[1] - user2_loc[1])**2)**0.5
                total_distance += distance
                pair_count += 1
                max_distance = max(max_distance, distance)
        
        if pair_count == 0:
            return 0
        
        avg_distance = total_distance / pair_count
        
        # Normalize: closer distances should give higher scores
        # Use an exponential decay function: score = e^(-avg_distance / scaling_factor)
        # Choose a scaling factor based on the data scale - this needs to be tuned
        scaling_factor = max_distance / 5 if max_distance > 0 else 1  # Adjust based on your distance scale
        distance_score = math.exp(-avg_distance / scaling_factor)
        
        return min(1.0, max(0.0, distance_score))

    def calculate_connection_score(self, community, social_network):
        """
        Calculate the social connection score for a community.
        
        Higher scores mean the community is more densely connected.
        
        Args:
            community (list): List of user IDs in the community
            social_network (SocialNetwork): The social network object containing relationship data
            
        Returns:
            float: Score between 0 and 1 indicating social connectivity
        """
        # Create a set of community members for faster lookups
        community_set = set(community)
        
        # Count internal connections and possible connections
        internal_connections = 0
        max_possible_connections = len(community) * (len(community) - 1) / 2  # Complete graph
        
        for user_id in community:
            # Get user's relationships
            relationships = social_network.getUserRel(user_id)
            
            if not relationships:
                continue
                
            # Count connections to other community members
            for rel in relationships:
                related_user = rel[0]
                
                if related_user in community_set and related_user != user_id:
                    # Add 0.5 to avoid double counting (each edge will be counted from both sides)
                    internal_connections += 0.5
        
        # Calculate density: actual connections / possible connections
        if max_possible_connections > 0:
            connection_density = internal_connections / max_possible_connections
        else:
            connection_density = 0
            
        return connection_density