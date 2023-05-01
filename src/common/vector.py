import math
import os
import json
from typing import List

from common import sides, util


# How much error to tolerate when simplifying the shape
SIMPLIFY_EPSILON = 1.5

# We'll merge vertices closer than this
MERGE_IF_CLOSER_THAN_PX = 1.75

# Opposing sides must be "parallel" within this threshold (in degrees)
SIDE_PARALLEL_THRESHOLD_DEG = 32

# Adjacent sides must be "orthogonal" within this threshold (in degrees)
SIDES_ORTHOGONAL_THRESHOLD_DEG = 42

# A side must be at least this long to be considered an edge
EDGE_WIDTH_MIN_RATIO = 0.4


class Vector(object):
    @staticmethod
    def from_file(filename, id) -> 'Vector':
        # Open image file
        binary_pixels, width, height = util.load_binary_image(filename)
        v = Vector(pixels=binary_pixels, width=width, height=height, id=id)
        return v

    def __init__(self, pixels, width, height, id) -> None:
        self.pixels = pixels
        self.width = width
        self.height = height
        self.dim = float(self.width + self.height) / 2.0
        self.id = id
        self.sides = []
        self.corners = []

    def process(self, output_path=None, render=False):
        self.find_border_raster()
        self.vectorize()

        try:
            self.find_four_corners()
            self.extract_four_sides()
        except Exception as e:
            self.render()
            print(f"Error while processing {self.id}:")
            raise e

        if render:
            self.render()

        if output_path:
            self.save(output_path)
        else:
            return self

    def save(self, output_path) -> None:
        full_svg_path = os.path.join(output_path, f"{self.id}_full.svg")
        colors = ['cc0000', '999900', '00aa99', '3300bb']
        svg = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        svg += f'<svg width="{3 * self.width}" height="{3 * self.height}" viewBox="-10 -10 {20 + self.width} {20 + self.height}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        for i, side in enumerate(self.sides):
            pts = ' '.join([','.join([str(e) for e in v]) for v in side.vertices])
            svg += f'<polyline points="{pts}" style="fill:none; stroke:#{colors[i]}; stroke-width:1.0" />'
        # draw in a small circle for each corner (the first and last vertex for each side)
        for i, side in enumerate(self.sides):
            v = side.vertices[0]
            svg += f'<circle cx="{v[0]}" cy="{v[1]}" r="{1.0}" style="fill:#000000; stroke-width:0" />'
        svg += f'<circle cx="{self.centroid[0]}" cy="{self.centroid[1]}" r="{1.0}" style="fill:#990000; stroke-width:0" />'
        svg += '</svg>'
        with open(full_svg_path, 'w') as f:
            f.write(svg)

        for i, side in enumerate(self.sides):
            side_path = os.path.join(output_path, f"side_{self.id}_{i}.json")
            data = {'piece_id': self.id, 'side_index': i, 'vertices': [list(v) for v in side.vertices], 'piece_center': list(side.piece_center), 'is_edge': side.is_edge}
            with open(side_path, 'w') as f:
                f.write(json.dumps(data))

    def find_border_raster(self) -> None:
        self.border = [[0 for i in range(self.width)] for j in range(self.height)]
        for y in range(1, self.height - 1):
            for x in range(1, self.width - 1):
                v = self.pixels[y][x]
                if v == 0:
                    continue

                neighbors = [
                    self.pixels[y - 1][x],  # above
                    self.pixels[y + 1][x],  # below
                    self.pixels[y][x - 1],  # left
                    self.pixels[y][x + 1],  # right
                ]
                if not all(neighbors):
                    self.border[y][x] = 1

    def vectorize(self) -> None:
        """
        We want to "wind" a string around the border
        So we find the top-left most border pixel, then sweep a polyline around the border
        As we go, we capture how much the angle of the polyline changes at each step
        """
        sx, sy = None, None

        # start at the first border pixel we find
        for y, row in enumerate(self.border):
            if any(row):
                sy = y
                sx = row.index(1)
                break

        if sx is None or sy is None:
            raise Exception(f"Piece @ {self.id} has no border to walk")

        self.vertices = [(sx, sy)]
        cx, cy = sx, sy
        p_angle = 0

        closed = False
        while not closed:
            neighbors = [
                # Clockwise sweep
                (cx,     cy - 1),  # above
                (cx + 1, cy - 1),  # above right
                (cx + 1, cy),      # right
                (cx + 1, cy + 1),  # below right
                (cx,     cy + 1),  # below
                (cx - 1, cy + 1),  # below left
                (cx - 1, cy),      # left
                (cx - 1, cy - 1),  # above left
            ]
            # pick where to start by looking at the current (absolute) angle, and looking
            # "back over our left shoulder" at the neighbor most in that direction, then sweep CW around the neighbors
            shift = int(round(p_angle * float(len(neighbors))/(2 * math.pi)))  # scale to wrap the full circle over the number of neighbors

            bx, by = cx, cy

            # check each neighbor in order to see if it is also a border
            # once we find one that is a border, add a point to it and continue
            for i in range(0 + shift, 8 + shift):
                nx, ny = neighbors[i % len(neighbors)]
                n = self.border[ny][nx]
                if n == 1:
                    dx, dy = nx - cx, ny - cy
                    abs_angle = math.atan2(dy, dx)
                    rel_angle = abs_angle - p_angle
                    p_angle = abs_angle

                    if rel_angle < 0:
                        rel_angle += 2 * math.pi

                    self.vertices.append((cx, cy))

                    cx, cy = nx, ny
                    if cx == sx and cy == sy:
                        closed = True

                    break

            if bx == cx and by == cy:
                raise Exception(f"Piece @ {self.id} will get us stuck in a loop because the border goes up to the edge of the bitmap. Take a new picture with the piece centered better or make sure the background is brighter white.")

        self.centroid = util.centroid(self.vertices)

    def merge_close_points(self, vs, threshold):
        i = -len(vs)
        while i < len(vs):
            i = i % len(vs)
            j = (i + 1) % len(vs)
            if util.distance(vs[i], vs[j]) <= threshold:
                min_v = util.midpoint_along_path(vs, vs[i], vs[j])

                # if the two points are next to each other, don't take the latter one, or else we'll then advance along the path indefinitely if there are more neighboring points
                if min_v == vs[j]:
                    min_v = vs[i]

                vs[i] = min_v
                vs.pop(j)
            else:
                i += 1

    def find_four_corners(self):
        # let's further simplify the shape, because this will lengthen the gap between vertices on flat parts
        vertices = self.vertices

        possible_corners = []

        # to find a corner, we're going to compute the angle between 3 consecutive points
        # if it is roughly 90º and pointed toward the center, it's a corner
        for i in range(len(vertices)):
            p_i = vertices[i]
            debug =(p_i[1] == 703)
            if debug:
                print(f"\n\n\n!!!!!!!!!!!!!! {p_i} !!!!!!!!!!!!!!!\n\n\n")

            # find the angle from i to the points before it (h), and i to the points after (j)
            vec_offset = 1  # we start comparing to this many points away, as really short vectors have noisy angles
            vec_len = 11  # compare this many total points
            a_ih, stdev_h = util.colinearity(from_point=p_i, to_points=util.slice(vertices, i-vec_len-vec_offset, i-vec_offset-1), debug=debug)
            a_ij, stdev_j = util.colinearity(from_point=p_i, to_points=util.slice(vertices, i+vec_offset+1, i+vec_len+vec_offset), debug=debug)
            stdev = (stdev_h + stdev_j)/2

            if stdev > 0.2:
                continue

            if debug:
                print(f"a_ih: {round(a_ih * 180/math.pi)} stdev_h: {stdev_h}")
                print(f"a_ij: {round(a_ij * 180/math.pi)} stdev_j: {stdev_j}")
                print(util.slice(vertices, i-vec_len-vec_offset, i-vec_offset-1))
                print(util.slice(vertices, i+vec_offset+1, i+vec_len+vec_offset))

            p_h = (p_i[0] + 10 * math.cos(a_ih), p_i[1] + 10 * math.sin(a_ih))
            p_j = (p_i[0] + 10 * math.cos(a_ij), p_i[1] + 10 * math.sin(a_ij))

            # how wide is the angle between the two legs?
            angle_hij = util.counterclockwise_angle_between_vectors(p_h, p_i, p_j)

            # See if the delta between the two legs is roughly 90º
            is_roughly_90 = abs(math.pi/2 - angle_hij) < SIDES_ORTHOGONAL_THRESHOLD_DEG * math.pi/180
            if not is_roughly_90:
                if debug:
                    print(f"not roughly 90º: {round(angle_hij * 180/math.pi)}")
                continue

            # corners generally open up toward the center of the piece
            # meaning the mid-angle that comes out of the corner is roughly the same as the angle from the corner to the center
            angle_ih = util.angle_between(p_i, p_h)
            a_ic = util.angle_between(p_i, self.centroid)
            opens_toward_angle = util.angle_between(p_i, util.midpoint(p_h, p_j))
            offset_from_center = util.compare_angles(opens_toward_angle, a_ic)
            is_pointed_toward_center = offset_from_center < angle_hij / 2

            is_corner = is_roughly_90 and is_pointed_toward_center
            if is_corner:
                # print(f"Found possible corner at {i}: {p_i} w/ {stdev}")
                # print(f"\t c={self.centroid} \t ih={round(angle_ih * 180 / math.pi)} \t ic={round(a_ic * 180 / math.pi)} \t ij={round(a_ij * 180 / math.pi)} \t offset={round(offset_from_center * 180 / math.pi)}")
                # print(f"\t angle width: {round(angle_hij * 180 / math.pi)}")
                # print(f"\t roughly 90? {is_roughly_90} \t toward center? {is_pointed_toward_center} \t open toward {round(opens_toward_angle * 180 / math.pi)} \t offset from center {round(offset_from_center * 180 / math.pi)}")
                possible_corners.append((i, p_i, angle_hij, stdev, offset_from_center))
            elif debug:
                print(f"NOT a possible corner at {i}: {p_i} w/ {stdev}")
                print(f"\t c={self.centroid} \t ih={round(angle_ih * 180 / math.pi)} \t ic={round(a_ic * 180 / math.pi)} \t ij={round(a_ij * 180 / math.pi)} \t offset={round(offset_from_center * 180 / math.pi)}")
                print(f"\t angle width: {round(angle_hij * 180 / math.pi)}")
                print(f"\t roughly 90? {is_roughly_90} \t toward center? {is_pointed_toward_center} \t open toward {round(opens_toward_angle * 180 / math.pi)} \t offset from center {round(offset_from_center * 180 / math.pi)}\n")

        # we often find a handful of points right near the corner
        # let's go through and pick the best of those
        eliminated_corner_indices = []
        for i, corner, angle, stdev, offset_from_center in possible_corners:
            if i in eliminated_corner_indices:
                # if we've been ruled out, no work to do
                continue

            for j, corner_j, angle, stdev_j, _ in possible_corners:
                # if we're close to another candidate, figure out if we're the better corner
                if i != j and util.distance(corner, corner_j) < 10:
                    # choose the corner thats furthest from the center of the piece, meaning it juts out the most
                    d_centroid_i = util.distance(corner, self.centroid)
                    d_centroid_j = util.distance(corner_j, self.centroid)
                    if d_centroid_i >= d_centroid_j:
                        eliminated_corner_indices.append(j)

        possible_corners = [c for c in possible_corners if c[0] not in eliminated_corner_indices]

        if len(possible_corners) < 4:
            print(eliminated_corner_indices)
            raise Exception(f"Expected 4 corners, but only found {len(possible_corners)} on piece {self.id}")

        def _score_corner(angle, stdev, offset_from_center, angle_to_opposite_corner, closest_corners_distance):
            # how much bigger are we than 90º? If we're less, then we're more likely to be a corner
            angle_error = max(0, angle - math.pi/2)

            # how close to other corners are we?
            proximity_penalty = self.dim / max(closest_corners_distance, 1)

            score = (0.5 * angle_to_opposite_corner) + (1.0 * angle_error) + (1.5 * offset_from_center) + \
                    (0.2 * stdev) + (0.2 * proximity_penalty)
            # print(f"CORNER[{v_i}]: {v_corner} \t opposite: {round(angle_to_opposite_corner * 180/math.pi)} \t angle error: {angle_error} \t offset: {offset_from_center} \t proximity_penalty: {proximity_penalty} \t ==> mix: {score}")
            return score

        # we still often end up with more than 4 corners
        # let's find the 4 "best" corners
        while len(possible_corners) > 4:
            # we determine "worst" by a mix of:
            # - do we have a corner on the other side of the piece? All pieces have a corner that's pretty much 180º around the centroid
            # - how far from 90º the angle is
            # - how non-straight the spokes are
            max_score = 0
            max_i = 0
            for i, (v_i, v_corner, angle, stdev, offset_from_center) in enumerate(possible_corners):
                # compare to positions of other corners
                angle_to_opposite_corner = float("inf")
                opposite_j = None
                closest_dist = float("inf")
                sec_closest_dist = float("inf")
                for j, (_, v_corner_j, _, _, _) in enumerate(possible_corners):
                    if v_corner != v_corner_j:
                        opposing_corner_angle = util.counterclockwise_angle_between_vectors(v_corner, self.centroid, v_corner_j)
                        delta_180 = util.compare_angles(opposing_corner_angle, math.pi)
                        # print(f"Comparing {v_corner} to {v_corner_j}: open angle: {round(opposing_corner_angle * 180 / math.pi)}º, delta 180º: {round(delta_180 * 180 / math.pi)}")
                        if delta_180 < angle_to_opposite_corner:
                            angle_to_opposite_corner = delta_180
                            opposite_j = j

                        dist = util.distance(v_corner, v_corner_j)
                        if dist < closest_dist:
                            sec_closest_dist = closest_dist
                            closest_dist = dist

                score = _score_corner(angle, stdev, offset_from_center, angle_to_opposite_corner, closest_dist + sec_closest_dist)
                if score > max_score:
                    max_score = score
                    max_i = i

            popped = possible_corners.pop(max_i)
            # print(f"Popped a bad corner: {popped}")

        self.corners = [c[1] for c in possible_corners]
        self.corner_indices = [c[0] for c in possible_corners]

        # the four corners should be roughly 90º from each other
        # we'll use the angle between the spokes to determine this
        corner_angles = [util.angle_between(self.centroid, c) for c in self.corners]
        for i in range(4):
            j = (i + 1) % 4
            angle = corner_angles[i]
            angle_next = corner_angles[j]
            angle_between = util.compare_angles(angle, angle_next)
            delta_90 = util.compare_angles(math.pi/2, angle_between)
            if delta_90 > 45 * math.pi/180:
                raise Exception(f"Corner angles are not roughly 90º: {round(angle * 180 / math.pi)}º and {round(angle_next * 180 / math.pi)}º = {round(angle_between * 180 / math.pi)}º apart, on piece {self.id}")

    def extract_four_sides(self) -> None:
        """
        Once we've found the corners, we'll identify which vertices belong to each side
        We do some validation to make sure the geometry of the piece is sensible
        """
        self.sides = []

        for i in range(4):
            # yank out all the relevant vertices for this side
            j = (i + 1) % 4
            c_i = self.corner_indices[i]
            c_j = self.corner_indices[j]
            vertices = util.slice(self.vertices, c_i, c_j)

            # do a bit of simplification
            vertices = util.ramer_douglas_peucker(vertices, epsilon=0.25)
            self.merge_close_points(vertices, threshold=MERGE_IF_CLOSER_THAN_PX)

            # make sure to include the true endpoints
            if vertices[0] != self.corners[i]:
                vertices.insert(0, self.corners[i])
            if vertices[-1] != self.corners[j]:
                vertices.append(self.corners[j])

            # edges are flat and thus have very little variance from the average line between all points
            _, stdev = util.colinearity(from_point=vertices[0], to_points=vertices[1:])
            is_edge = stdev < 0.06

            side = sides.Side(piece_id=self.id, side_id=None, vertices=vertices, piece_center=self.centroid, is_edge=is_edge)
            self.sides.append(side)

        # we need to find 4 sides
        if len(self.sides) != 4:
            raise Exception(f"Expected 4 sides, found {len(self.sides)} on piece {self.id}")

        # opposite sides should be parallel
        if abs(self.sides[0].angle - self.sides[2].angle) > SIDE_PARALLEL_THRESHOLD_DEG:
            raise Exception(f"Expected sides 0 and 2 to be parallel, but they are not ({self.sides[0].angle - self.sides[2].angle})")

        if abs(self.sides[1].angle - self.sides[3].angle) > SIDE_PARALLEL_THRESHOLD_DEG:
            raise Exception(f"Expected sides 1 and 3 to be parallel, but they are not ({self.sides[1].angle - self.sides[3].angle})")

        # make sure that sides 0 and 1 are roughly at a right angle
        if abs(self.sides[1].angle - self.sides[0].angle - 90 * math.pi/180.0) >  SIDES_ORTHOGONAL_THRESHOLD_DEG:
            raise Exception(f"Expected sides 0 and 1 to be at a right angle, but they are not ({self.sides[1].angle} - {self.sides[0].angle})")

        lengths = [s.length for s in self.sides]
        len_ratio02 = abs(lengths[0] - lengths[2])/lengths[0]
        len_ratio13 = abs(lengths[1] - lengths[3])/lengths[1]
        if len_ratio02 > 0.55 or len_ratio13 > 0.55:
            raise Exception(f"Expected sides to be roughly the same length, but they are not ({len_ratio02}, {len_ratio13})")

        d02 = util.distance_between_segments(self.sides[0].segment, self.sides[2].segment)
        d13 = util.distance_between_segments(self.sides[0].segment, self.sides[2].segment)
        if d02 > 1.35 * d13 or d13 > 1.35 * d02:
            raise Exception(f"Expected the piece to be roughly square, but the distance between sides is not comparable ({d02} vs {d13})")

        edge_count = sum([s.is_edge for s in self.sides])
        if edge_count > 2:
            raise Exception(f"A piece cannot be a part of more than 2 edges, found {edge_count}")
        elif edge_count == 2:
            if (self.sides[0].is_edge and self.sides[2].is_edge) or (self.sides[1].is_edge and self.sides[3].is_edge):
                raise Exception("A piece cannot be a part of two edges that are parallel!")

    def render(self) -> None:
        SIDE_COLORS = [util.RED, util.GREEN, util.PURPLE, util.CYAN]
        CORNER_COLOR = util.YELLOW
        lines = []
        for row in self.pixels:
            line = []
            for pixel in row:
                line.append('# ' if pixel == 1 else '. ')
            lines.append(line)

        i = 0
        for si, side in enumerate(self.sides):
            for (px, py) in side.vertices:
                color = SIDE_COLORS[si % len(SIDE_COLORS)]
                if py >= len(lines) or px >= len(lines[py]):
                    continue
                lines[py][px] = f"{color}{str(i % 10)} {util.WHITE}"

        for (px, py) in self.corners:
            value = lines[py][px].split(' ')[0][-1]
            lines[py][px] = f"{util.BLACK_ON_BLUE}{value} {util.WHITE}"

        lines[self.centroid[1]][self.centroid[0]] = f"{util.BLACK_ON_RED}X {util.WHITE}"

        print(f' {util.GRAY} ' + 'v ' * self.width + f"{util.WHITE}")
        for i, line in enumerate(lines):
            line = ''.join(line)
            print(f'{util.GRAY}> {util.WHITE}{line}{util.GRAY}<{util.WHITE} {i}')
        print(f' {util.GRAY} ' + '^ ' * self.width + f"{util.WHITE}")

    def compare(self, piece) -> float:
        """
        Compare this piece to another piece, returning a score of how similar they are
        0 = no error
        higher = more error
        """
        min_cumulative_error = None
        for start_i in range(4):
            cumulative_error = 0
            for p1_side_i in range(4):
                p0_side_i = (p1_side_i + start_i) % 4
                error = self.sides[p0_side_i].error_when_fit_with(piece[p1_side_i], flip=False, render=False)
                if error is None:
                    cumulative_error = None
                    break
                else:
                    cumulative_error += error

            if min_cumulative_error is None or (cumulative_error is not None and cumulative_error < min_cumulative_error):
                min_cumulative_error = cumulative_error

        return min_cumulative_error