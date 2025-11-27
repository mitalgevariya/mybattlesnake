import os
import random
from flask import Flask, request, jsonify
from collections import deque

app = Flask(__name__)

# Cache for board center calculations
_board_center_cache = {}


@app.route("/")
def index():
    """
    Root endpoint - returns Battlesnake metadata
    """
    return jsonify({
        "apiversion": "1",
        "author": "FunkySnake",
        "color": "#FF00FF",
        "head": "silly",
        "tail": "curled"
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
    my_id = game_data["you"]["id"]
    my_length = len(my_body)
    my_health = game_data["you"]["health"]
    food = board["food"]
    all_snakes = board["snakes"]
    board_width = board["width"]
    board_height = board["height"]

    # Filter out ourselves from opponents using ID for safety
    opponents = [s for s in all_snakes if s["id"] != my_id]

    # All possible moves
    possible_moves = ["up", "down", "left", "right"]

    # Analyze each move with detailed scoring
    move_scores = {}

    for move in possible_moves:
        new_head = get_new_head_position(my_head, move)

        # Basic safety check
        if not is_basic_safe(new_head, board_width, board_height, my_body, food):
            continue

        # STRICT SAFETY: Never move into opponent bodies
        if check_opponent_bodies(new_head, opponents, food):
            continue

        # STRICT SAFETY: Avoid head-to-head with equal/larger snakes
        if not validate_move_against_opponents(new_head, my_length, opponents, board_width, board_height):
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

        # Step 3: FINAL SAFETY CHECK - Validate chosen move against opponent threats
        chosen_head = get_new_head_position(my_head, chosen_move)
        is_safe_from_larger = validate_move_against_opponents(
            chosen_head, my_length, opponents, board_width, board_height
        )

        if not is_safe_from_larger:
            # Chosen move is dangerous! Find alternative
            print(f"⚠️ Move {chosen_move} blocked by larger/equal snake! Re-evaluating...")

            # Remove the dangerous move and try alternatives
            safe_alternatives = []
            for alt_move, alt_score in sorted(move_scores.items(), key=lambda x: x[1], reverse=True):
                if alt_move == chosen_move:
                    continue
                alt_head = get_new_head_position(my_head, alt_move)
                if validate_move_against_opponents(alt_head, my_length, opponents, board_width, board_height):
                    safe_alternatives.append((alt_move, alt_score))

            if safe_alternatives:
                # Choose best safe alternative
                chosen_move = safe_alternatives[0][0]
                print(f"✅ Switching to safer move: {chosen_move}")
            else:
                # No safe alternatives, keep original (might lose but try)
                print(f"⚠️ No safe alternatives! Proceeding with {chosen_move} anyway")

        # Log strategy
        strategy = determine_strategy(my_health, my_length, opponents, food)
        print(f"🎯 {strategy}: {chosen_move} (score: {move_scores.get(chosen_move, 0):.2f}, health: {my_health})")

    return jsonify({"move": chosen_move})


@app.route("/end", methods=["POST"])
def end():
    """
    Called when the game ends
    """
    game_data = request.get_json()
    print(f"Game ended: {game_data['game']['id']}")
    return "ok"


def is_basic_safe(new_head, board_width, board_height, my_body, food=None):
    """
    Basic safety: wall and self-collision check only
    """
    # Check if out of bounds
    if new_head["x"] < 0 or new_head["x"] >= board_width:
        return False
    if new_head["y"] < 0 or new_head["y"] >= board_height:
        return False

    # Prevent moving backwards (neck check) - critical for length 2
    if len(my_body) >= 2:
        neck = my_body[1]
        if new_head["x"] == neck["x"] and new_head["y"] == neck["y"]:
            return False

    # Check if hitting own body
    # We check the entire body first
    for i, segment in enumerate(my_body):
        if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
            # Collision detected with a body segment

            # Exception: If it's the tail (last segment) AND we are not eating
            # Note: If snake is stacked (just ate), the tail segment is duplicated.
            # The duplicate (second to last) will NOT be the last segment, so it will trigger collision.
            # This correctly handles stacked tails.
            if i == len(my_body) - 1:
                # Check if eating
                is_eating = False
                if food:
                    for f in food:
                        if new_head["x"] == f["x"] and new_head["y"] == f["y"]:
                            is_eating = True
                            break

                if not is_eating:
                    # Safe to move into tail if not eating
                    continue

            # Not the tail, or we are eating -> Collision
            return False

    return True


def validate_move_against_opponents(chosen_head, my_length, opponents, board_width, board_height):
    """
    FINAL SAFETY VALIDATION: Check if any equal/larger opponent can reach this position
    Returns True if safe, False if dangerous
    """
    if not opponents:
        return True  # No opponents, always safe

    chosen_pos = (chosen_head["x"], chosen_head["y"])

    for opponent in opponents:
        opponent_head = opponent["head"]
        opponent_length = len(opponent["body"])

        # Only worry about equal or larger snakes
        if opponent_length < my_length:
            continue

        # Get all possible next positions for this opponent
        opponent_possible_moves = get_possible_moves(opponent_head, board_width, board_height)

        # Check if opponent can reach our chosen position
        for opp_next_pos in opponent_possible_moves:
            if (opp_next_pos["x"], opp_next_pos["y"]) == chosen_pos:
                # DANGER! Equal or larger opponent can move here
                return False

    return True  # No equal/larger opponents can reach this position


def evaluate_move(move, new_head, my_head, my_body, my_length, my_health,
                  opponents, food, board_width, board_height):
    """
    Optimized move scoring with balanced strategic factors
    """
    score = 0.0

    # Factor 1: Straight line movement (save health)
    if len(my_body) >= 2 and is_straight_line(my_body, move):
        score += 6.0

    # Factor 2: Collision avoidance (instant fail)
    if check_opponent_bodies(new_head, opponents, food):
        return -1000.0

    # Factor 2.5: Self-collision backup check (redundant but safe)
    # Check full body to be absolutely sure we don't hit ourselves
    # This might prevent tail-chasing in some edge cases but prevents death
    for segment in my_body[:-1]:
        if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
            return -1000.0

    # Pre-calculate opponent size comparisons (optimize repeated checks)
    if opponents:
        opp_sizes = [len(opp["body"]) for opp in opponents]
        all_bigger = all(size > my_length for size in opp_sizes)
        any_smaller = any(size < my_length for size in opp_sizes)

        # Calculate size gaps for smarter strategy
        max_opponent_size = max(opp_sizes)
        min_opponent_size = min(opp_sizes)
        size_gap_from_largest = max_opponent_size - my_length
        size_gap_from_smallest = my_length - min_opponent_size
    else:
        all_bigger = False
        any_smaller = False
        max_opponent_size = 0
        min_opponent_size = 0
        size_gap_from_largest = 0
        size_gap_from_smallest = 0

    # Factor 3: Head-to-head collision strategy
    head_score = evaluate_head_to_head(new_head, my_length, opponents, board_width, board_height)
    score += head_score

    # Count opponents for crowded board detection
    num_opponents = len(opponents) if opponents else 0

    # Factor 4: Adaptive strategy with size-gap awareness
    if my_health < 15:
        # CRITICAL: Food only (desperate)
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 4.5
    elif size_gap_from_largest >= 2:
        # CLOSE THE GAP: We're 2+ shorter than largest snake - grow aggressively
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 4.0
        if my_health >= 20:
            score += evaluate_underdog_avoidance(new_head, my_length, opponents, board_width, board_height) * 2.5
    elif size_gap_from_smallest >= 2 and my_health > 50:
        # TOO DOMINANT: We're 2+ longer than smallest - maintain but don't grow more
        # Focus on survival and position, avoid food unless critical
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 0.2  # Very low priority
        score += evaluate_hunting(new_head, my_length, opponents, board_width, board_height) * 2.0
        score += evaluate_blocking(new_head, my_length, my_health, opponents, board_width, board_height) * 2.5
    elif my_health > 20 and num_opponents >= 2:
        # CONSERVATIVE MODE: Multiple opponents and healthy - prioritize survival
        # Avoid food competition, focus on space and safety
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 0.1  # Very low priority

        # If hunting smaller snakes, be cautious
        if any_smaller:
            score += evaluate_hunting(new_head, my_length, opponents, board_width, board_height) * 1.0  # Reduced

        # High priority on avoiding danger
        if all_bigger or not any_smaller:
            score += evaluate_underdog_avoidance(new_head, my_length, opponents, board_width, board_height) * 3.0
    elif all_bigger:
        # UNDERDOG: Growth focus
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 3.5
        if my_health >= 20:
            score += evaluate_underdog_avoidance(new_head, my_length, opponents, board_width, board_height) * 2.0
    elif my_health >= 20 and any_smaller:
        # COMPETITIVE: Balanced approach
        score += evaluate_hunting(new_head, my_length, opponents, board_width, board_height) * 2.0
        score += evaluate_blocking(new_head, my_length, my_health, opponents, board_width, board_height) * 1.5
        if food and num_opponents < 2:
            # Moderate food priority to stay competitive (1-2 ahead)
            score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 1.5
    else:
        # SURVIVAL: Balanced
        score += evaluate_food_seeking(new_head, my_head, food, opponents, my_length) * 2.0

    # Factor 5: Space control (critical for survival)
    space_score = evaluate_space_advanced(new_head, my_body, opponents, board_width, board_height)
    score += space_score * 2.0

    # Factor 6: Center control (only when healthy and long enough)
    if my_health >= 25 and my_length >= 5:
        center_score = evaluate_center_control(new_head, my_body, my_length, board_width, board_height, opponents)
        score += center_score * 2.0

    # Factor 7: Area coverage (only when dominant)
    if my_health >= 30 and my_length >= 8:
        coverage_score = evaluate_area_coverage(new_head, my_body, my_length, my_health,
                                                opponents, board_width, board_height)
        score += coverage_score * 1.5

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


def check_opponent_bodies(new_head, opponents, food=None):
    """
    Optimized: Check if move hits any opponent body
    """
    new_pos = (new_head["x"], new_head["y"])
    for opponent in opponents:
        body = opponent["body"]

        # Default: Tail moves, so we don't check it
        segments_to_check = body[:-1]

        # BUT: If opponent is about to eat, they grow, and tail stays
        if food:
            opp_head = opponent["head"]
            is_about_to_eat = False
            for f in food:
                if abs(opp_head["x"] - f["x"]) + abs(opp_head["y"] - f["y"]) == 1:
                    is_about_to_eat = True
                    break

            if is_about_to_eat:
                segments_to_check = body # Check full body including tail

        for segment in segments_to_check:
            if (segment["x"], segment["y"]) == new_pos:
                return True
    return False


def evaluate_head_to_head(new_head, my_length, opponents, board_width, board_height):
    """
    DEFENSIVE head-to-head strategy: AVOID equal/larger snakes, seek only smaller ones
    Returns -1000 (instant fail) if collision possible with equal/larger snake
    """
    score = 0.0

    for opponent in opponents:
        opponent_head = opponent["head"]
        opponent_length = len(opponent["body"])

        # Get possible opponent moves
        opp_possible_moves = get_possible_moves(opponent_head, board_width, board_height)

        for opp_move in opp_possible_moves:
            if new_head["x"] == opp_move["x"] and new_head["y"] == opp_move["y"]:
                # Potential head-to-head collision detected!
                if my_length > opponent_length:
                    # We're bigger - safe to engage
                    score += 50.0
                else:
                    # Equal or larger snake - ABORT THIS MOVE COMPLETELY
                    # This is a survival game - never risk equal/larger collisions
                    return -1000.0  # Instant fail, same as hitting a wall

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
    queue = deque([(start_pos["x"], start_pos["y"], 0)])

    while queue:
        x, y, depth = queue.popleft()

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
    queue = deque([(new_head["x"], new_head["y"], 0)])

    while queue:
        x, y, depth = queue.popleft()

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
    queue = deque([(new_head["x"], new_head["y"], 0)])

    while queue:
        x, y, depth = queue.popleft()

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


def evaluate_center_control(new_head, my_body, my_length, board_width, board_height, opponents=None):
    """
    Smart center control: avoid opponent bodies and their next possible moves
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

    # SAFE CENTER POSITIONING: Avoid opponent bodies and predicted moves
    if opponents:
        for opponent in opponents:
            opp_head = opponent["head"]
            opp_body = opponent["body"]

            # Check proximity to opponent bodies
            for segment in opp_body:
                dist_to_segment = abs(new_head["x"] - segment["x"]) + abs(new_head["y"] - segment["y"])
                if dist_to_segment <= 1:
                    # Too close to opponent body
                    score -= 30.0
                elif dist_to_segment == 2:
                    # Near opponent body
                    score -= 10.0

            # Predict where opponent might move next turn
            opponent_next_moves = get_possible_moves(opp_head, board_width, board_height)
            for next_pos in opponent_next_moves:
                # If our new position is where opponent might move
                if new_head["x"] == next_pos["x"] and new_head["y"] == next_pos["y"]:
                    # DANGER: Opponent could move here next turn
                    score -= 40.0
                # If opponent might move adjacent to us
                elif abs(new_head["x"] - next_pos["x"]) + abs(new_head["y"] - next_pos["y"]) == 1:
                    score -= 15.0

            # Extra penalty for being near opponent heads (danger zone)
            head_distance = abs(new_head["x"] - opp_head["x"]) + abs(new_head["y"] - opp_head["y"])
            if head_distance <= 2:
                # Very close to opponent head - risky
                score -= 25.0
            elif head_distance <= 3:
                # Somewhat close - caution
                score -= 10.0

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
    num_opponents = len(opponents) if opponents else 0

    if my_health < 15:
        return "🚨 CRITICAL - FOOD NOW"

    # Calculate size gaps
    if opponents:
        opp_sizes = [len(o["body"]) for o in opponents]
        max_opponent_size = max(opp_sizes)
        min_opponent_size = min(opp_sizes)
        size_gap_from_largest = max_opponent_size - my_length
        size_gap_from_smallest = my_length - min_opponent_size
        all_opponents_bigger = all(size > my_length for size in opp_sizes)
        any_smaller = any(size < my_length for size in opp_sizes)
    else:
        return "👑 SOLO - DOMINATING"

    # Size-gap based strategy
    if size_gap_from_largest >= 2:
        return f"📈 CLOSING GAP ({size_gap_from_largest} behind)"
    elif size_gap_from_smallest >= 2 and my_health > 50:
        return f"🛑 TOO LONG ({size_gap_from_smallest} ahead) - MAINTAIN"
    elif my_health > 20 and num_opponents >= 2:
        return "🛡️ CONSERVATIVE - SURVIVAL"
    elif all_opponents_bigger:
        if my_health >= 20:
            return "📈 UNDERDOG - GROWING"
        else:
            return "🍎 UNDERDOG - SURVIVAL"
    elif my_health >= 20 and any_smaller:
        return "⚔️ COMPETITIVE MODE"
    elif my_health < 20:
        return "🍎 SURVIVAL MODE"
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
