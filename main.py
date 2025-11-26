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
    Called every turn - return your move decision
    """
    game_data = request.get_json()

    # Get game board information
    board = game_data["board"]
    my_head = game_data["you"]["head"]
    my_body = game_data["you"]["body"]
    my_length = len(my_body)
    my_health = game_data["you"]["health"]
    food = board["food"]
    opponents = board["snakes"]

    # All possible moves
    possible_moves = ["up", "down", "left", "right"]
    safe_moves = []

    # Step 1: Eliminate moves that hit walls, own body, or other snakes
    board_width = board["width"]
    board_height = board["height"]

    for move in possible_moves:
        if is_move_safe(move, my_head, board_width, board_height, my_body, opponents, my_length):
            safe_moves.append(move)

    # Step 2: If no safe moves, pick any move (we're doomed anyway)
    if len(safe_moves) == 0:
        print(f"No safe moves available! Moving down")
        chosen_move = "down"
    else:
        # Step 3: Prioritize moves based on food and strategy
        if my_health < 30 or len(food) > 0:
            # When hungry or food available, move towards nearest food
            food_move = get_move_towards_food(my_head, food, safe_moves)
            if food_move:
                chosen_move = food_move
                print(f"Moving {chosen_move} towards food (health: {my_health})")
            else:
                chosen_move = random.choice(safe_moves)
                print(f"Moving {chosen_move} (no food path)")
        else:
            # When healthy, prefer center and avoid edges
            chosen_move = get_best_positional_move(my_head, safe_moves, board_width, board_height)
            print(f"Moving {chosen_move} (positional)")

    return jsonify({"move": chosen_move})


@app.route("/end", methods=["POST"])
def end():
    """
    Called when the game ends
    """
    game_data = request.get_json()
    print(f"Game ended: {game_data['game']['id']}")
    return "ok"


def is_move_safe(move, head, board_width, board_height, body, opponents, my_length):
    """
    Check if a move is safe (doesn't hit wall, self, or other snakes)
    """
    # Calculate new head position
    new_head = get_new_head_position(head, move)

    # Check if out of bounds
    if new_head["x"] < 0 or new_head["x"] >= board_width:
        return False
    if new_head["y"] < 0 or new_head["y"] >= board_height:
        return False

    # Check if hitting own body (excluding tail since it moves)
    for segment in body[:-1]:
        if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
            return False

    # Check if hitting other snakes
    for opponent in opponents:
        # Skip checking ourselves
        if opponent["body"] == body:
            continue

        # Check opponent's body (excluding tail)
        for segment in opponent["body"][:-1]:
            if new_head["x"] == segment["x"] and new_head["y"] == segment["y"]:
                return False

        # Avoid head-to-head collisions with larger or equal snakes
        opponent_head = opponent["head"]
        opponent_length = len(opponent["body"])

        # Check if we could collide head-to-head
        opponent_possible_moves = get_possible_moves(opponent_head, board_width, board_height)
        for opp_move in opponent_possible_moves:
            if new_head["x"] == opp_move["x"] and new_head["y"] == opp_move["y"]:
                # Head-to-head collision possible
                if opponent_length >= my_length:
                    # Avoid if opponent is same size or larger
                    return False

    return True


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


def get_move_towards_food(my_head, food, safe_moves):
    """
    Find the best move to get closer to the nearest food
    """
    if not food or not safe_moves:
        return None

    # Find nearest food
    nearest_food = min(food, key=lambda f: get_distance(my_head, f))

    # Score each safe move by how close it gets us to food
    best_move = None
    best_distance = float('inf')

    for move in safe_moves:
        new_head = get_new_head_position(my_head, move)
        distance = get_distance(new_head, nearest_food)

        if distance < best_distance:
            best_distance = distance
            best_move = move

    return best_move


def get_best_positional_move(my_head, safe_moves, board_width, board_height):
    """
    Choose move that keeps us towards the center and gives us space
    """
    if not safe_moves:
        return None

    center_x = board_width / 2
    center_y = board_height / 2
    center = {"x": center_x, "y": center_y}

    # Prefer moves that keep us closer to center
    best_move = None
    best_score = float('-inf')

    for move in safe_moves:
        new_head = get_new_head_position(my_head, move)

        # Distance to center (lower is better)
        center_distance = get_distance(new_head, center)

        # Distance from edges (higher is better)
        edge_distance = min(
            new_head["x"],
            new_head["y"],
            board_width - 1 - new_head["x"],
            board_height - 1 - new_head["y"]
        )

        # Combined score: prefer center and avoid edges
        score = edge_distance * 2 - center_distance

        if score > best_score:
            best_score = score
            best_move = move

    return best_move if best_move else random.choice(safe_moves)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
