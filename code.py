
x0,y0 = x,y = 0,0
x1,y1 = 10,5

Dx = x1-x0
Dy = y1-y0

steps = max(abs(Dx),abs(Dy))

step_x = Dx/steps
step_y = Dy/steps

points=[]

for _ in range(steps+1):
    points.append((round(x),round(y)))             
    x += step_x
    y += step_y

def draw_empty_rectangle(points:list , width: int, height: int, border_char: str = '*', drawing_char='"', fill_char: str = ' ') -> None:
    """
    Draws an empty rectangle in the terminal.

    Args:
        width: The width of the rectangle.
        height: The height of the rectangle.
        border_char: The character to use for the border. Defaults to '*'.
        fill_char: The character to use for the inside of the rectangle. Defaults to ' '.
    """
    if width <= 0 or height <= 0:
        print("Width and height must be positive integers.")
        return

    for r in range(height):
        row_str = ""
        for c in range(width):

            # Check if it's the first or last row
            if r == 0 or r == height - 1:
                row_str += border_char
            # Check if it's the first or last column (for inner rows)
            elif c == 0 or c == width - 1:
                row_str += border_char
            # Otherwise, it's an inner cell
            else:
                if (c,r) in points:
                    row_str += drawing_char
                else:
                    row_str += fill_char
        print(row_str)

# --- Example Usage ---
if __name__ == "__main__":
    print("Drawing a 10x5 rectangle with default characters:")
    draw_empty_rectangle(points,20, 20)


