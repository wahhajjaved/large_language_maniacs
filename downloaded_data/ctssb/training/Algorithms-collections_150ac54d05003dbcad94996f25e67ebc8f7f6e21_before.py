# https://see.stanford.edu/materials/icspacs106b/H19-RecBacktrackExamples.pdf
# Function: SolveSudoku
# Takes a partially filled-in grid and fill all the cells such that it doesn't have any conflict with
# the row, column and box.
# The pseudocode for backtracking algorithm is:
# Find row, col of an unassigned cell
# If there is none, return true
#   For digits from 1 to 9
#       if there is no conflict for digit at row,col
#           assign digit to row,col and recursively try fill in rest of grid
#           if recursion successful, return true
#           if !successful, remove digit and try another
# if all digits have been tried and nothing worked, return false to trigger backtracking

UNASSIGNED = False


class Grid(object):
    def __init__(self, num_rows=9, num_cols=9):
        self.num_rows = num_rows
        self.num_cols = num_cols
        self.cell = [[UNASSIGNED] * num_cols for row in range(num_rows)]


def find_unassigned_location(grid, row_col):
    for row in range(grid.num_rows):
        for col in range(grid.num_cols):
            if grid.cell[row][row] == UNASSIGNED:
                row_col[0], row_col[1]=row, col
                return True
    return False


def used_in_row(grid, row_col, num):
    for col in range(grid.num_cols):
        if grid.cell[row_col[0]][col] == num:
            return True
    return False


def used_in_col(grid, row_col, num):
    for row in range(grid.num_rows):
        if grid.cell[row][row_col[1]] == num:
            return True
    return False


def used_in_box(grid, row_col, num):
    box_start_row = row_col[0] - row_col[0] % 3
    box_start_col = row_col[1] - row_col[1] % 3

    for row in range(3):
        for col in range(3):
            if grid.cell[row + box_start_row][col + box_start_col] == num:
                return True
    return False


def no_conflicts(grid, row_col, num):
    return not used_in_row(grid, row_col, num) and not used_in_col(grid, row_col, num) \
           and not used_in_box(grid, row_col, num)


def solve_sudoku(grid):
    row_col = [0, 0]
    if not find_unassigned_location(grid, row_col):         # If all are assigned success
        return True

    for num in range(1, 10):                                # Try from 1 to 9
        if no_conflicts(grid, row_col, num):                # If the num is not in conflict
            grid.cell[row_col[0]][row_col[1]] = num         # assigned it
            if solve_sudoku(grid):                          # recur, if success
                return True
            grid.cell[row_col[0]][row_col[1]] = UNASSIGNED  # not valid, unassigned

    return False                                            # trigger backtrack, all available options are exhaust


def display_grid(grid):
    for row in range(grid.num_rows):
        for col in range(grid.num_cols):
            print(grid.cell[row][col], end="  ")
        print()
    print()

if __name__ == "__main__":
    grid = Grid()
    solve_sudoku(grid)
    display_grid(grid)


