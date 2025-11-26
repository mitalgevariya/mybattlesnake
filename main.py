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

    # Factor 1: Straight line movement bonus (save health)
    if is_straight_line(my_body, move):
        score += 5.0

    # Factor 2: Avoid opponent bodies
    body_danger = check_opponent_bodies(new_head, opponents)
    if body_danger:
        return -1000.0  # Instant death

    # Factor 3: Head-to-head collision strategy
    head_score = evaluate_head_to_head(new_head, my_length, opponents, board_width, board_height)
    score += head_score

    # Factor 4: Food strategy based on health
    if my_health < 40:
        # Low health: prioritize food aggressively
        food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
        score += food_score * 3.0
    elif my_health > 70 and opponents:
        # High health: hunt weaker snakes
        hunt_score = evaluate_hunting(new_head, my_length, opponents, board_width, board_height)
        score += hunt_score * 2.0
    else:
        # Medium health: balance food and positioning
        food_score = evaluate_food_seeking(new_head, my_head, food, opponents, my_length)
        score += food_score * 1.5

    # Factor 5: Space control and avoid traps
    space_score = evaluate_space(new_head, my_body, opponents, board_width, board_height)
    score += space_score

    # Factor 6: Board position (prefer center slightly)
    position_score = evaluate_position(new_head, board_width, board_height)
    score += position_score * 0.5

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
    Smart food seeking that avoids opponent interference
    """
    if not food:
        return 0.0

    score = 0.0

    # Find nearest food
    nearest_food = min(food, key=lambda f: get_distance(my_head, f))
    distance_to_food = get_distance(new_head, nearest_food)
    current_distance = get_distance(my_head, nearest_food)

    # Reward moving closer to food
    if distance_to_food < current_distance:
        score += 20.0
        # Bonus for being very close
        if distance_to_food <= 1:
            score += 30.0
    elif distance_to_food > current_distance:
        score -= 5.0

    # Check if opponent is closer to this food
    for opponent in opponents:
        opp_distance = get_distance(opponent["head"], nearest_food)
        if opp_distance < distance_to_food and len(opponent["body"]) >= my_length:
            # Larger opponent is closer, look for different food
            score -= 15.0

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


def evaluate_space(new_head, my_body, opponents, board_width, board_height):
    """
    Flood fill to check available space (avoid traps)
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


def evaluate_position(new_head, board_width, board_height):
    """
    Slight preference for center positions
    """
    center_x = board_width / 2
    center_y = board_height / 2

    distance_from_center = abs(new_head["x"] - center_x) + abs(new_head["y"] - center_y)
    max_distance = center_x + center_y

    # Small bonus for being near center
    return (max_distance - distance_from_center) * 0.5


def determine_strategy(my_health, my_length, opponents, food):
    """
    Determine current strategy for logging
    """
    if my_health < 40:
        return "🍎 FOOD SEEKING"
    elif my_health > 70 and opponents and any(len(o["body"]) < my_length for o in opponents):
        return "⚔️ HUNTING"
    elif not opponents:
        return "👑 DOMINATING"
    else:
        return "🎮 BALANCED"


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
