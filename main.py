import os
import random
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    """
    Root endpoint - returns Battlesnake metadata
    """
    return jsonify({
        "apiversion": "1",
        "author": "BigDog",
        "color": "#C0C0C0",
        "head": "rudolph",
        "tail": "coffee"
    })


@app.route("/start", methods=["POST"])
def start():
    """
    Called at the start of each game
    """
    game_data = request.get_json()
    print(f"Game starting: {game_data['game']['id']}")
    return "ok"


@app.route("/move", methods=["POST"])
def move():
    """
    Called every turn - return your move decision with advanced strategy
    """
    game_data = request.get_json()

    # Get game board information
    board = game_data["board"]
    my_head = game_data["you"]["head"]
    my_body = game_data["you"]["body"]
    my_length = len(my_body)
    my_health = game_data["you"]["health"]
    food = board["food"]
    all_snakes = board["snakes"]
    board_width = board["width"]
    board_height = board["height"]

    # Filter out ourselves from opponents
    opponents = [s for s in all_snakes if s["body"] != my_body]

    # All possible moves
    possible_moves = ["up", "down", "left", "right"]

    # Analyze each move with detailed scoring
    move_scores = {}

    for move in possible_moves:
        new_head = get_new_head_position(my_head, move)

        # Basic safety check
        if not is_basic_safe(new_head, board_width, board_height, my_body):
            continue

        # Advanced scoring for this move
        score = evaluate_move(
            move, new_head, my_head, my_body, my_length, my_health,
            opponents, food, board_width, board_height
        )
        move_scores[move] = score

    # Step 2: If no safe moves, try to survive
    if len(move_scores) == 0:
        print(f"⚠️ No safe moves! Attempting survival move")
        chosen_move = "down"
    else:
        # Choose highest scoring move
        chosen_move = max(move_scores, key=move_scores.get)

        # Log strategy
        strategy = determine_strategy(my_health, my_length, opponents, food)
        print(f"🎯 {strategy}: {chosen_move} (score: {move_scores[chosen_move]:.2f}, health: {my_health})")

    return jsonify({"move": chosen_move})


@app.route("/end", methods=["POST"])
def end():
    """
    Called when the game ends
    """
    game_data = request.get_json()
    print(f"Game ended: {game_data['game']['id']}")
    return "ok"


def is_basic_safe(new_head, board_width, board_height, my_body):
    """
    Basic safety: wall and self-collision check only
    """
    # Check if out of bounds
    if new_head["x"] < 0 or new_head["x"] >= board_width:
        return False
    if new_head["y"] < 0 or new_head["y"] >= board_height:
        return False

    # Check if hitting own body (excluding tail since it moves)
    for segment in my_body[:-1]:
        if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
            return False

    return True


def evaluate_move(move, new_head, my_head, my_body, my_length, my_health,
                  opponents, food, board_width, board_height):
    """
    Score a move based on multiple strategic factors
    """
    score = 0.0

    # Factor 1: Straight line movement bonus (save health - critical!)
    if is_straight_line(my_body, move):
        score += 8.0  # Strong preference to continue straight

    # Factor 2: Avoid opponent bodies
    body_danger = check_opponent_bodies(new_head, opponents)
    if body_danger:
        return -1000.0  # Instant death

    # Factor 3: Head-to-head collision strategy
    head_score = evaluate_head_to_head(new_head, my_length, opponents, board_width, board_height)
    score += head_score

    # Factor 4: Dynamic strategy based on size and health
    # Check if we're the underdog (all opponents are bigger)
    all_opponents_bigger = all(len(opp["body"]) > my_length for opp in opponents) if opponents else False
    any_smaller_opponent = any(len(opp["body"]) < my_length for opp in opponents) if opponents else False

    if my_health < 15:
        # Critical health: MUST get food NOW regardless of size
        food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
        score += food_score * 5.0  # Extremely high priority
    elif all_opponents_bigger:
        # UNDERDOG MODE: Focus on growth to catch up
        if my_health >= 20:
            # Healthy underdog: aggressive growth strategy
            food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
            score += food_score * 4.0  # Very high priority - need to grow!

            # Avoid larger snakes while growing
            avoidance_score = evaluate_underdog_avoidance(new_head, my_length, opponents, board_width, board_height)
            score += avoidance_score * 2.5
        else:
            # Low health underdog: careful growth
            food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
            score += food_score * 3.0
    elif my_health >= 20 and any_smaller_opponent:
        # DOMINANT MODE: Enough health and we're competitive or larger
        hunt_score = evaluate_hunting(new_head, my_length, opponents, board_width, board_height)
        score += hunt_score * 3.0

        # Try to block and control opponents
        blocking_score = evaluate_blocking(new_head, my_length, my_health, opponents, board_width, board_height)
        score += blocking_score * 2.0

        # Still look for food opportunistically but with lower priority
        if food:
            food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
            score += food_score * 0.5  # Low priority, only if convenient
    else:
        # SURVIVAL MODE: Low health (15-19) or equal size competition
        food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
        score += food_score * 2.0

    # Factor 5: Lookahead - avoid dead ends by checking future moves
    lookahead_score = evaluate_lookahead(new_head, my_body, opponents, board_width, board_height, depth=3)
    score += lookahead_score * 3.0  # High priority - prevents getting trapped

    # Factor 6: Enhanced space control - prefer less cramped areas
    space_score = evaluate_space_advanced(new_head, my_body, opponents, board_width, board_height)
    score += space_score * 2.5  # Increased importance

    # Factor 6: Center control and territorial dominance
    center_score = evaluate_center_control(new_head, my_body, my_length, board_width, board_height)
    score += center_score * 3.0  # High priority for center control

    # Factor 7: Area coverage - use body to block maximum area
    coverage_score = evaluate_area_coverage(new_head, my_body, my_length, my_health,
                                            opponents, board_width, board_height)
    score += coverage_score * 2.0

    return score


def is_straight_line(body, move):
    """
    Check if move continues in same direction (saves health)
    """
    if len(body) < 2:
        return False

    head = body[0]
    neck = body[1]

    current_direction = None
    if head["x"] > neck["x"]:
        current_direction = "right"
    elif head["x"] < neck["x"]:
        current_direction = "left"
    elif head["y"] > neck["y"]:
        current_direction = "up"
    elif head["y"] < neck["y"]:
        current_direction = "down"

    return current_direction == move


def check_opponent_bodies(new_head, opponents):
    """
    Check if move hits any opponent body
    """
    for opponent in opponents:
        # Check all body segments except tail (it will move)
        for segment in opponent["body"][:-1]:
            if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
                return True
    return False


def evaluate_head_to_head(new_head, my_length, opponents, board_width, board_height):
    """
    Aggressive head-to-head strategy: seek smaller snakes, avoid larger ones
    """
    score = 0.0

    for opponent in opponents:
        opponent_head = opponent["head"]
        opponent_length = len(opponent["body"])

        # Get possible opponent moves
        opp_possible_moves = get_possible_moves(opponent_head, board_width, board_height)

        for opp_move in opp_possible_moves:
            if new_head["x"] == opp_move["x"] and new_head["y"] == opp_move["y"]:
                # Potential head-to-head collision
                if my_length > opponent_length:
                    # We're bigger! GO FOR THE KILL
                    score += 50.0
                elif my_length == opponent_length:
                    # Equal size: avoid (both die)
                    score -= 100.0
                else:
                    # They're bigger: RUN AWAY
                    score -= 200.0

        # Also score proximity to smaller snake heads (hunting)
        if my_length > opponent_length:
            distance_to_opp = get_distance(new_head, opponent_head)
            if distance_to_opp < 3:
                score += (3 - distance_to_opp) * 10  # Get closer to hunt

    return score


def evaluate_food_seeking(new_head, my_head, food, opponents, my_length):
    """
    Smart food seeking that avoids opponent interference and minimizes moves
    """
    if not food:
        return 0.0

    score = 0.0

    # Find nearest accessible food
    nearest_food = min(food, key=lambda f: get_distance(my_head, f))
    distance_to_food = get_distance(new_head, nearest_food)
    current_distance = get_distance(my_head, nearest_food)

    # Reward moving closer to food
    if distance_to_food < current_distance:
        score += 25.0
        # Extra bonus for direct path (Manhattan distance decreases by 1)
        if current_distance - distance_to_food == 1:
            score += 10.0  # Reward efficient straight path
        # Huge bonus for being very close
        if distance_to_food == 0:
            score += 100.0  # About to eat!
        elif distance_to_food == 1:
            score += 40.0
    elif distance_to_food > current_distance:
        score -= 10.0  # Penalty for moving away

    # Check if opponent is closer to this food
    contested = False
    for opponent in opponents:
        opp_distance = get_distance(opponent["head"], nearest_food)
        if opp_distance < distance_to_food:
            if len(opponent["body"]) >= my_length:
                # Larger opponent is closer, look for different food
                score -= 20.0
                contested = True
            elif len(opponent["body"]) < my_length:
                # Smaller opponent is closer, we can fight for it
                score -= 5.0

    # If food is contested, try to find alternative food
    if contested and len(food) > 1:
        other_foods = [f for f in food if f != nearest_food]
        if other_foods:
            alt_food = min(other_foods, key=lambda f: get_distance(my_head, f))
            alt_distance = get_distance(new_head, alt_food)
            if alt_distance < get_distance(my_head, alt_food):
                score += 15.0  # Bonus for moving toward uncontested food

    return score


def evaluate_hunting(new_head, my_length, opponents, board_width, board_height):
    """
    Hunt smaller snakes when we're strong
    """
    score = 0.0

    for opponent in opponents:
        opponent_length = len(opponent["body"])
        opponent_head = opponent["head"]

        if my_length > opponent_length:
            # Target smaller snakes
            distance = get_distance(new_head, opponent_head)

            # Get close to cut them off
            if distance <= 3:
                score += (4 - distance) * 15
            elif distance <= 5:
                score += (6 - distance) * 5

    return score


def evaluate_underdog_avoidance(new_head, my_length, opponents, board_width, board_height):
    """
    Avoid larger snakes while focusing on growth (underdog mode)
    """
    score = 0.0

    for opponent in opponents:
        opponent_length = len(opponent["body"])
        opponent_head = opponent["head"]

        if opponent_length > my_length:
            # Keep distance from larger snakes
            distance = get_distance(new_head, opponent_head)

            if distance <= 2:
                # Too close to larger snake - danger!
                score -= 30.0
            elif distance <= 4:
                # Somewhat close - keep distance
                score -= (5 - distance) * 8
            elif distance >= 6:
                # Good distance - safe to grow
                score += 5.0

            # Extra penalty for moving towards larger snake heads
            current_distance = get_distance(opponent_head, {"x": new_head["x"] - (new_head["x"] - opponent_head["x"]),
                                                             "y": new_head["y"] - (new_head["y"] - opponent_head["y"])})
            if distance < current_distance:
                # Moving closer to larger snake - bad idea
                score -= 15.0

    return score


def evaluate_blocking(new_head, my_length, my_health, opponents, board_width, board_height):
    """
    Block opponents' escape routes when we're healthy and strong
    """
    score = 0.0

    # Only block if we have sufficient health to sustain the strategy
    if my_health < 30:
        return 0.0

    for opponent in opponents:
        opponent_head = opponent["head"]
        opponent_length = len(opponent["body"])

        # Get opponent's available moves
        opp_possible_moves = get_possible_moves(opponent_head, board_width, board_height)

        # Check if we can block any of their escape routes
        for opp_move in opp_possible_moves:
            distance_to_their_move = get_distance(new_head, opp_move)

            # If we're adjacent to where they might move
            if distance_to_their_move <= 1:
                if my_length > opponent_length:
                    # We're bigger, blocking is good - cut off their options
                    score += 20.0
                elif my_length == opponent_length:
                    # Equal size, moderate blocking value
                    score += 5.0

        # Extra points for positioning between opponent and open space
        opponent_space = count_reachable_space(opponent_head, opponent["body"], opponents,
                                               board_width, board_height, my_length)
        if opponent_space < 15:  # They're already cramped
            distance = get_distance(new_head, opponent_head)
            if distance <= 2 and my_length > opponent_length:
                # Move closer to trap them further
                score += 15.0

    return score


def count_reachable_space(start_pos, own_body, opponents, board_width, board_height, exclude_length):
    """
    Count how much space is reachable from a position (for blocking evaluation)
    """
    accessible = 0
    max_check = 6
    visited = set()
    queue = [(start_pos["x"], start_pos["y"], 0)]

    while queue:
        x, y, depth = queue.pop(0)

        if depth >= max_check:
            continue

        if (x, y) in visited:
            continue

        if x < 0 or x >= board_width or y < 0 or y >= board_height:
            continue

        # Check if occupied
        occupied = False
        for segment in own_body[:-1]:
            if x == segment["x"] and y == segment["y"]:
                occupied = True
                break

        if not occupied:
            for opponent in opponents:
                if len(opponent["body"]) == exclude_length:
                    continue  # Skip the snake we're measuring for
                for segment in opponent["body"][:-1]:
                    if x == segment["x"] and y == segment["y"]:
                        occupied = True
                        break

        if occupied:
            continue

        visited.add((x, y))
        accessible += 1

        queue.append((x + 1, y, depth + 1))
        queue.append((x - 1, y, depth + 1))
        queue.append((x, y + 1, depth + 1))
        queue.append((x, y - 1, depth + 1))

    return accessible


def evaluate_space(new_head, my_body, opponents, board_width, board_height):
    """
    Flood fill to check available space (avoid traps) - DEPRECATED
    Use evaluate_space_advanced instead
    """
    # Simple space check: count accessible squares within small radius
    accessible = 0
    max_check = 4

    visited = set()
    queue = [(new_head["x"], new_head["y"], 0)]

    while queue:
        x, y, depth = queue.pop(0)

        if depth >= max_check:
            continue

        if (x, y) in visited:
            continue

        if x < 0 or x >= board_width or y < 0 or y >= board_height:
            continue

        # Check if occupied
        occupied = False
        for segment in my_body[:-1]:
            if x == segment["x"] and y == segment["y"]:
                occupied = True
                break

        if not occupied:
            for opponent in opponents:
                for segment in opponent["body"][:-1]:
                    if x == segment["x"] and y == segment["y"]:
                        occupied = True
                        break

        if occupied:
            continue

        visited.add((x, y))
        accessible += 1

        # Add neighbors
        queue.append((x + 1, y, depth + 1))
        queue.append((x - 1, y, depth + 1))
        queue.append((x, y + 1, depth + 1))
        queue.append((x, y - 1, depth + 1))

    # More space = better
    return accessible * 2


def evaluate_lookahead(new_head, my_body, opponents, board_width, board_height, depth=3):
    """
    Lookahead function: Simulates future moves to check if path leads to dead-end
    Returns the number of safe moves available before getting trapped
    """
    if depth == 0:
        return 0

    # Simulate moving to new_head position
    simulated_body = [dict(new_head)] + my_body[:-1]  # Add new head, remove tail

    # Count safe next moves from this position
    safe_moves = 0
    future_scores = []

    for direction in ["up", "down", "left", "right"]:
        next_pos = get_new_head_position(new_head, direction)

        # Check if this next move is safe
        if not is_basic_safe(next_pos, board_width, board_height, simulated_body, None):
            continue

        # Check against opponents
        if check_opponent_bodies(next_pos, opponents, None):
            continue

        safe_moves += 1

        # Recursively check if this path continues to be safe
        if depth > 1:
            future_safe = evaluate_lookahead(next_pos, simulated_body, opponents,
                                            board_width, board_height, depth - 1)
            future_scores.append(future_safe)

    # Score based on:
    # 1. Number of immediate safe moves
    # 2. Average safety of future paths
    immediate_score = safe_moves * 10
    future_score = sum(future_scores) / len(future_scores) if future_scores else 0

    return immediate_score + future_score


def evaluate_space_advanced(new_head, my_body, opponents, board_width, board_height):
    """
    Advanced space evaluation - prefer open areas with multiple escape routes
    """
    # Multi-depth flood fill to evaluate both immediate and future space
    immediate_space = 0  # 1-2 moves away
    extended_space = 0   # 3-6 moves away
    max_immediate = 3
    max_extended = 7

    visited = set()
    queue = [(new_head["x"], new_head["y"], 0)]

    while queue:
        x, y, depth = queue.pop(0)

        if depth >= max_extended:
            continue

        if (x, y) in visited:
            continue

        if x < 0 or x >= board_width or y < 0 or y >= board_height:
            continue

        # Check if occupied by snakes
        occupied = False
        for segment in my_body[:-1]:
            if x == segment["x"] and y == segment["y"]:
                occupied = True
                break

        if not occupied:
            for opponent in opponents:
                for segment in opponent["body"][:-1]:
                    if x == segment["x"] and y == segment["y"]:
                        occupied = True
                        break

        if occupied:
            continue

        visited.add((x, y))

        # Weight closer spaces more heavily
        if depth < max_immediate:
            immediate_space += 1
        else:
            extended_space += 1

        # Add neighbors
        queue.append((x + 1, y, depth + 1))
        queue.append((x - 1, y, depth + 1))
        queue.append((x, y + 1, depth + 1))
        queue.append((x, y - 1, depth + 1))

    # Calculate open directions (multiple escape routes)
    open_directions = 0
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        check_x = new_head["x"] + dx
        check_y = new_head["y"] + dy

        if 0 <= check_x < board_width and 0 <= check_y < board_height:
            occupied = False
            for segment in my_body[:-1]:
                if check_x == segment["x"] and check_y == segment["y"]:
                    occupied = True
                    break

            if not occupied:
                for opponent in opponents:
                    for segment in opponent["body"][:-1]:
                        if check_x == segment["x"] and check_y == segment["y"]:
                            occupied = True
                            break

            if not occupied:
                open_directions += 1

    # Scoring formula:
    # - Immediate space is critical (nearby freedom)
    # - Extended space matters for long-term planning
    # - Multiple open directions = less cramped (bonus)
    score = (immediate_space * 4.0) + (extended_space * 1.5) + (open_directions * 8.0)

    # Penalty for being too cramped (< 2 directions)
    if open_directions < 2:
        score -= 20.0

    # Bonus for having many options (3-4 directions)
    if open_directions >= 3:
        score += 15.0

    return score


def evaluate_position(new_head, board_width, board_height):
    """
    Slight preference for center positions - DEPRECATED
    Use evaluate_center_control instead
    """
    center_x = board_width / 2
    center_y = board_height / 2

    distance_from_center = abs(new_head["x"] - center_x) + abs(new_head["y"] - center_y)
    max_distance = center_x + center_y

    # Small bonus for being near center
    return (max_distance - distance_from_center) * 0.5


def evaluate_center_control(new_head, my_body, my_length, board_width, board_height):
    """
    Strong preference for center control and territorial dominance
    """
    center_x = board_width / 2
    center_y = board_height / 2
    score = 0.0

    # Distance from center (closer is better)
    distance_from_center = abs(new_head["x"] - center_x) + abs(new_head["y"] - center_y)
    max_distance = center_x + center_y

    # Strong reward for being near center
    center_bonus = (max_distance - distance_from_center) * 5.0
    score += center_bonus

    # Extra bonus for being IN the center (within 2 squares)
    if distance_from_center <= 2:
        score += 25.0
    elif distance_from_center <= 4:
        score += 10.0

    # Penalty for being on edges
    edge_distance = min(
        new_head["x"],
        new_head["y"],
        board_width - 1 - new_head["x"],
        board_height - 1 - new_head["y"]
    )

    if edge_distance == 0:
        # On the wall - bad for center control
        score -= 15.0
    elif edge_distance == 1:
        # One square from wall
        score -= 8.0

    # Bonus for longer snakes controlling center (more intimidating)
    if my_length > 8 and distance_from_center <= 3:
        score += my_length * 1.5

    return score


def evaluate_area_coverage(new_head, my_body, my_length, my_health,
                           opponents, board_width, board_height):
    """
    Use body positioning to control maximum area and block opponents
    """
    score = 0.0

    # Only focus on area control when we're healthy and have decent length
    if my_health < 20 or my_length < 5:
        return 0.0

    # Calculate which quadrants our body covers
    quadrants_covered = set()
    center_x = board_width / 2
    center_y = board_height / 2

    for segment in my_body:
        qx = 0 if segment["x"] < center_x else 1
        qy = 0 if segment["y"] < center_y else 1
        quadrants_covered.add((qx, qy))

    # Reward covering multiple quadrants (territorial control)
    quadrant_bonus = len(quadrants_covered) * 8.0
    score += quadrant_bonus

    # Check if new head position adds new quadrant coverage
    new_qx = 0 if new_head["x"] < center_x else 1
    new_qy = 0 if new_head["y"] < center_y else 1
    new_quadrant = (new_qx, new_qy)

    if new_quadrant not in quadrants_covered:
        # Moving into new quadrant - expand territory!
        score += 20.0

    # Evaluate how our body divides the board (blocking strategy)
    # Check if our body creates barriers that split opponent areas
    if my_length >= 8:
        blocking_value = evaluate_body_blocking(new_head, my_body, opponents,
                                                board_width, board_height, center_x, center_y)
        score += blocking_value

    # Bonus for body spreading (not coiled up)
    body_spread = calculate_body_spread(my_body, board_width, board_height)
    score += body_spread * 3.0

    return score


def evaluate_body_blocking(new_head, my_body, opponents, board_width, board_height, center_x, center_y):
    """
    Score how well our body blocks and divides the board
    """
    score = 0.0

    # Create a wall effect: body segments forming lines
    if len(my_body) < 8:
        return 0.0

    # Check for horizontal/vertical lines in body
    horizontal_lines = {}
    vertical_lines = {}

    for segment in my_body:
        y = segment["y"]
        x = segment["x"]

        if y not in horizontal_lines:
            horizontal_lines[y] = []
        horizontal_lines[y].append(x)

        if x not in vertical_lines:
            vertical_lines[x] = []
        vertical_lines[x].append(y)

    # Reward long continuous lines (wall effect)
    for y, x_coords in horizontal_lines.items():
        if len(x_coords) >= 4:
            # Long horizontal wall
            score += len(x_coords) * 3.0

    for x, y_coords in vertical_lines.items():
        if len(y_coords) >= 4:
            # Long vertical wall
            score += len(y_coords) * 3.0

    # Extra bonus if body crosses through center creating division
    center_crossed = False
    for segment in my_body:
        if abs(segment["x"] - center_x) <= 1 or abs(segment["y"] - center_y) <= 1:
            center_crossed = True
            break

    if center_crossed and len(my_body) >= 10:
        score += 15.0

    # Check if we're blocking opponent access to areas
    for opponent in opponents:
        opp_head = opponent["head"]

        # See if our body is between opponent and center
        segments_between = 0
        for segment in my_body:
            # Simple check: is segment between opponent and center
            if (opp_head["x"] < segment["x"] < center_x or center_x < segment["x"] < opp_head["x"]) and \
               (opp_head["y"] < segment["y"] < center_y or center_y < segment["y"] < opp_head["y"]):
                segments_between += 1

        if segments_between >= 3:
            # We're forming a barrier between opponent and center
            score += 12.0

    return score


def calculate_body_spread(my_body, board_width, board_height):
    """
    Calculate how spread out the body is (good for area control)
    """
    if len(my_body) < 4:
        return 0.0

    # Calculate bounding box of our body
    min_x = min(seg["x"] for seg in my_body)
    max_x = max(seg["x"] for seg in my_body)
    min_y = min(seg["y"] for seg in my_body)
    max_y = max(seg["y"] for seg in my_body)

    # Area covered by bounding box
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    coverage_area = width * height

    # Normalize by board size
    board_area = board_width * board_height
    spread_ratio = coverage_area / board_area

    # Higher spread = better area control
    return spread_ratio * 50.0


def determine_strategy(my_health, my_length, opponents, food):
    """
    Determine current strategy for logging
    """
    if my_health < 15:
        return "🚨 CRITICAL - FOOD NOW"

    # Check if we're the underdog
    all_opponents_bigger = all(len(o["body"]) > my_length for o in opponents) if opponents else False
    any_smaller = any(len(o["body"]) < my_length for o in opponents) if opponents else False

    if all_opponents_bigger:
        if my_health >= 20:
            return "📈 UNDERDOG - GROWING"
        else:
            return "🍎 UNDERDOG - SURVIVAL"
    elif my_health >= 20 and any_smaller:
        return "⚔️ HUNTING MODE"
    elif my_health < 20:
        return "🍎 SURVIVAL MODE"
    elif not opponents:
        return "👑 DOMINATING"
    else:
        return "🎮 EFFICIENT PLAY"


def get_new_head_position(head, move):
    """
    Calculate new head position after a move
    """
    new_head = dict(head)

    if move == "up":
        new_head["y"] += 1
    elif move == "down":
        new_head["y"] -= 1
    elif move == "left":
        new_head["x"] -= 1
    elif move == "right":
        new_head["x"] += 1

    return new_head


def get_possible_moves(head, board_width, board_height):
    """
    Get all possible next positions from a head position
    """
    moves = []
    directions = ["up", "down", "left", "right"]

    for direction in directions:
        new_pos = get_new_head_position(head, direction)
        if 0 <= new_pos["x"] < board_width and 0 <= new_pos["y"] < board_height:
            moves.append(new_pos)

    return moves


def get_distance(point1, point2):
    """
    Calculate Manhattan distance between two points
    """
    return abs(point1["x"] - point2["x"]) + abs(point1["y"] - point2["y"])




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
