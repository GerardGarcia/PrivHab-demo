import os
import sys
import argparse
import math
import random
import operator
import time
import threading
import logging
import signal
import copy
import traceback

import pygame as pg

# Demo dependencies
from lib.spritesheet import spritesheet
import lib.menusystem as ms
sys.path.append(os.path.abspath('lib/'))

COLOR_DICT = {
    "green": "green",
    "red": "red3",
    "grey": "grey",
    "yellow": "yellow"
}

DIRECT_DICT = {pg.K_LEFT: (-1, 0),
               pg.K_RIGHT: (1, 0),
               pg.K_UP: (0, -1),
               pg.K_DOWN: (0, 1)}
#  X and Y Component magnitude when moving at 45 degree angles
ANGLE_UNIT_SPEED = math.sqrt(2) / 2


def get_random_position(margins):
    left_margin = int((GlobalVars.SCREEN_SIZE[0] / 100.0) * margins[0])
    rigth_margin = int((GlobalVars.SCREEN_SIZE[0] / 100.0) * margins[1])
    top_margin = int((GlobalVars.SCREEN_SIZE[1] / 100.0) * margins[2])
    bottom_margin = int((GlobalVars.SCREEN_SIZE[1] / 100.0) * margins[3])

    random_position = [random.randint(left_margin, GlobalVars.SCREEN_SIZE[0] - rigth_margin),
                       random.randint(top_margin, GlobalVars.SCREEN_SIZE[1] - bottom_margin)]

    return random_position


class GlobalVars:

    """
    Everything is an object in python, therefore GlobalVars
    references to a class without methods (basically a struct) which contains the global variables.

    This way we can access its members from anywhere (including threads).
    """

    def __init__(self):
        pass
    RUNNING = True
    SCREEN_SIZE = [1024, 768]


class Mario(spritesheet):

    """
    Represents a character from a spritesheet.

    It wrappers how we get the correct image (a Surface object) based on the direction
    and the movement of the character.

    It also contains surfaces representing its Home and Workplaces

    TODO: Load an array of Surfaces at inizialisation so we do not have to calcualte
    each time the position of the image in the spritesheet.
    """

    def __init__(self, color, initial_posiiton=(0, 0), direction=0, movement=0):
        self.color = color
        spritesheet.__init__(self, os.path.abspath("data/mario_{0}.png".format(color)))
        self.background = pg.color.Color('white')
        self.direction = direction
        self.movement = movement

        # Image parameters
        self.x_off = 8  # Spritesheet start (x)
        self.y_off = 4  # Spritesheet start (y)
        self.x_width = 16  # Sprite width (x)
        self.y_width = 32  # Sprite width (y)
        self.x_inter_width = 5  # Horitzontal space between sprites
        self.y_inter_width = 7  # Vertical space between sprites

        # Direction
        self.direction_off = 4  # Where is direction 0 (UP)
        self.direction_next = operator.sub  # Operator that gets the next direction (in order 0,1,2...)
        self.direction_num = 8  # Number of directions (should be 8)

        # Movement (we don't consider an offset, first image of the strip will be the first movement)
        self.movements = 8  # Images per direction

        # Home / Work
        self.home_image = pg.image.load(os.path.abspath("data/pipe_{0}.png".format(color)))
        self.home_image.set_colorkey(pg.color.Color("white"))
        # pg.Surface.convert_alpha(self.home_image)
        self.workplace_image = pg.image.load(os.path.abspath("data/castle_{0}.png".format(color)))
        self.home_image.set_colorkey(pg.color.Color("white"))
        # pg.Surface.convert_alpha(self.workplace_image)

        # Set actual coords
        self.set_image_coords()

        logging.debug("Created {0} spritesheet".format(self))

    def __str__(self):
        return "{0} {1}".format(self.color, self.__class__.__name__)

    def set_direction(self, direction):
        """ Sets the face direction of the character. """
        self.direction = direction

    def get_direction(self):
        """ Gets the configured face direction. """
        return self.direction

    pos = property(get_direction, set_direction)

    def set_image_coords(self):
        """ Set sprite coords from direction and movement number. """
        self.pos_x = self.x_off + (self.x_width * self.movement) + (self.x_inter_width * self.movement)
        real_direction = self.direction_next(self.direction_off, self.direction) % self.direction_num
        self.pos_y = self.y_off + real_direction * (self.y_width + self.y_inter_width)

    def first(self):
        self.movement = 0
        self.set_image_coords()

        return self.image_at((self.pos_x, self.pos_y, self.x_width, self.y_width), self.background)

    def next(self):
        """ Movement iterator. Returns next image. """
        self.movement = (self.movement + 1) % self.movements
        self.set_image_coords()

        return self.image_at((self.pos_x, self.pos_y, self.x_width, self.y_width), self.background)


class Habitat(object):

    """
    Represents a habitat.
    Supported shapes: circle, square, rectangle, ellipse
    """

    # Defaults
    DEFAULT_N = 20
    DEFAULT_BETA = 25
    DEFAULT_COLOR = "black"
    DEFAULT_SHAPE = "ellipse"
    DEFAULT_HABITAT_UPDATE_FREQ = 0.5  # Seconds
    DEFAULT_SHOWN_LAST_N_POINTS = False

    # Display parameters
    HABITAT_WIDTH = 3
    WIDTH_OFFSET = 0  # Pixels
    HEIGHT_OFFSET = -4  # Pixels (negative values higher the habitat position)
    LAST_N_POINTS_RADIUS_RATIO = 200  # Pixels

    def __init__(self, node_rect, color=DEFAULT_COLOR, n=DEFAULT_N, beta=DEFAULT_BETA, shape=DEFAULT_SHAPE,
                 show_last_n_points=DEFAULT_SHOWN_LAST_N_POINTS, update_freq=DEFAULT_HABITAT_UPDATE_FREQ):

        # Habitat configuration
        # We link the node_rect object to this Habitat so we don't need to pass
        # the node position each time the habitat is updated
        self.node_rect = node_rect
        self.color_str = color
        self.color_repr = pg.color.Color(COLOR_DICT[self.color_str])
        self.n = n
        self.alpha = 2.0 / (self.n + 1)
        self.beta = beta

        # Habitat attribtues
        self.update_freq = update_freq
        self.shape = shape
        # For circle / square
        self.circle_center = None
        self.circle_radius = 0
        # For rectangle / ellipse
        self.focus_1 = None
        self.focus_2 = None
        self.ellipse_center = None
        self.ellipse_radius = 0

        # Last N weighted points attributes
        self.show_last_n_points = show_last_n_points
        self.last_n_points_radius_ratio = self.LAST_N_POINTS_RADIUS_RATIO
        self.last_n_point_start = 0
        self.last_n_points = []

        # Renderized habitat
        self.habitat_surface = None
        self.habitat_surface_pos = None

        self.killed = False
        self.access_lock = threading.Lock()

    def update_thread(self):
        """
        Updates the habitat every self.update_freq seconds.
        """
        while GlobalVars.RUNNING and not self.killed:
            self.access_lock.acquire()

            current_location = self.get_center()

            logging.debug("[{0}] Current location: {1}".format(self, current_location))

            # Update circle / square
            if not self.circle_center and not (self.focus_1 or self.focus_2):
                self.circle_center = copy.copy(current_location)

            # Update circle_center
            self.circle_center = self.ewma_points(self.circle_center, current_location, self.alpha)

            logging.debug("[{0}] Updated circle center. Center: {1}".format(self, self.ellipse_center))

            # Update distance between current location and circle_center
            circle_distance = self.distance(self.circle_center, current_location)

            # Update radius
            self.circle_radius = circle_distance * self.alpha + self.circle_radius * (1.0 - self.alpha)

            logging.debug("[{0}] Updated circle radius. Radius: {1}".format(self, self.circle_radius))

            # Update rectangle / ellipse
            # First time set focus to current position
            if not (self.focus_1 or self.focus_2) and not self.ellipse_center:
                self.focus_1 = copy.copy(current_location)
                self.focus_2 = copy.copy(current_location)
            elif not (self.focus_1 or self.focus_2) and self.ellipse_center:
                self.focus_1 = copy.copy(self.ellipse_center)
                self.focus_2 = copy.copy(self.ellipse_center)

            logging.debug("[{0}] Old focus. Focus 1: {1} Focus 2: {2}"
                          .format(self, self.focus_1, self.focus_2))

            # Update focal points
            # Get nearer and farther focal point
            focus_1_distance = self.distance(self.focus_1, current_location)
            focus_2_distance = self.distance(self.focus_2, current_location)

            logging.debug("[{0}] Distance to current location. Focus 1: {1}, Focus 2: {2}"
                          .format(self, focus_1_distance, focus_2_distance))

            if focus_1_distance <= focus_2_distance:
                self.focus_1 = self.ewma_points(self.focus_1, current_location, self.alpha)
                self.focus_2 = self.ewma_points(self.focus_2, current_location, self.alpha / self.beta)
            else:
                self.focus_1 = self.ewma_points(self.focus_1, current_location, self.alpha / self.beta)
                self.focus_2 = self.ewma_points(self.focus_2, current_location, self.alpha)

            logging.debug("[{0}] Updated focus. Focus 1: {1} Focus 2: {2}"
                          .format(self, self.focus_1, self.focus_2))

            # Update ellipse_center
            self.ellipse_center = [(self.focus_1[0] + self.focus_2[0]) / 2, (self.focus_1[1] + self.focus_2[1]) / 2]

            logging.debug("[{0}] Updated ellipse center. Center: {1}".format(self, self.ellipse_center))

            # Update distance between current location and focus points
            focus_1_distance = self.distance(self.focus_1, current_location)
            focus_2_distance = self.distance(self.focus_2, current_location)
            ellipse_distance = focus_1_distance + focus_2_distance

            self.ellipse_radius = ellipse_distance * self.alpha + self.ellipse_radius * (1.0 - self.alpha)

            logging.debug("[{0}] Updated ellipse radius. Radius: {1}".format(self, self.ellipse_radius))

            # Add last point
            if self.show_last_n_points:
                if len(self.last_n_points) < self.n:
                    self.last_n_points.append(copy.copy(current_location))
                else:
                    self.last_n_points[self.last_n_point_start] = copy.copy(current_location)
                    self.last_n_point_start = (self.last_n_point_start + 1) % self.n

            self.access_lock.release()

            # Sleep until the next habitat update
            time.sleep(self.update_freq)

    def draw(self, surface):
        """ Draws a habitat and its last N points """
        self.access_lock.acquire()

        if (self.shape == "circle" or self.shape == "square") and self.circle_radius and self.circle_center and \
                self.circle_radius > self.HABITAT_WIDTH + 1:

            if self.shape == "circle":
                # pg.draw.circle(surface, pg.color.Color("black"), map(int, self.center),
                #                int(self.radius), self.HABITAT_WIDTH + 1)
                # pg.draw.circle(surface, pg.color.Color("black"), map(int, self.center),
                #                int(self.radius) + self.HABITAT_WIDTH, 1)
                pg.draw.circle(surface, self.color_repr, map(
                    int, self.circle_center), int(self.circle_radius), self.HABITAT_WIDTH)
            elif self.shape == "square":

                # Calculate edge length as twice the length of the radius
                edge = self.circle_radius * 2
                rect = pg.Rect(0, 0, edge, edge)
                rect.center = self.circle_center

                pg.draw.rect(surface, self.color_repr, rect, self.HABITAT_WIDTH)

        elif (self.shape == "ellipse" or self.shape == "rectangle") and self.focus_1 and self.focus_2 and \
                self.ellipse_center:

            # Calculate minimum rectangle that contains the ellipse with focus points
            # Major axis is a + b (a,b are the distances from each focus to any point on the ellipse (radius))
            # Minor axis is the hypotenuse of the triangle rectangle with edges major axis and distance
            # between focal points. We calculate Minor axis with Pitagoras.

            major_axis = self.ellipse_radius
            minor_axis = None

            focus_distance = self.distance(self.focus_2, self.focus_1)
            if pow(major_axis, 2) - pow(focus_distance, 2) > 0:
                minor_axis = math.sqrt(pow(major_axis, 2) - pow(focus_distance, 2))

            if minor_axis and minor_axis > self.HABITAT_WIDTH * 2 + 1:
                # Create minimum rectangle that contains the habitat
                rect = pg.Rect(0, 0, major_axis, minor_axis)

                # Draw habitat into intermediate surface
                habitat_surface = pg.Surface((major_axis, minor_axis))
                habitat_surface.set_colorkey(pg.color.Color("black"))
                if self.shape == "ellipse":
                    pg.draw.ellipse(habitat_surface, self.color_repr, rect, self.HABITAT_WIDTH)
                elif self.shape == "rectangle":
                    pg.draw.rect(habitat_surface, self.color_repr, rect, self.HABITAT_WIDTH)

                # Get inclination
                dx, dy = self.focus_1[0] - self.focus_2[0], self.focus_1[1] - self.focus_2[1]
                rads_angle = math.atan2(dx, dy)
                degs_angle = (math.degrees(rads_angle) + 90) % 360.0

                # Incline habitat if necessary
                if degs_angle != 0:
                    habitat_surface = pg.transform.rotate(habitat_surface, degs_angle)

                # Draw intermediate surface into surface
                position = [self.ellipse_center[0] - habitat_surface.get_width() / 2,
                            self.ellipse_center[1] - habitat_surface.get_height() / 2]
                surface.blit(habitat_surface, position)

        # Show last N points
        if self.show_last_n_points and self.last_n_points:

            next_point_pos = self.last_n_point_start
            for i in range(0, len(self.last_n_points)):

                # Calculate last N point weight
                weight = self.alpha * pow(1 - self.alpha, len(self.last_n_points) - i)

                # Draw point into Surface
                pg.draw.circle(surface,
                               self.color_repr,
                               map(int, self.last_n_points[next_point_pos]),
                               int(weight * self.last_n_points_radius_ratio))
                # Next point
                next_point_pos = (next_point_pos + 1) % len(self.last_n_points)

        self.access_lock.release()

    def __str__(self):
        return self.color_str

    def distance(self, point1, point2):
        distance = math.sqrt(pow(point2[0] - point1[0], 2.0) +
                             pow(point2[1] - point1[1], 2.0))
        if distance < 1e-5:
            distance = 0

        return distance

    def ewma_points(self, center_old, current_location, factor):
        return [current_loc_coord * factor + center_old_coord * (1.0 - factor)
                for center_old_coord, current_loc_coord in zip(center_old, current_location)]

    def get_center(self):
        """
        Calculates the center of the habitat from the node rectangle.
        takes into consideration HEIGHT_OFFSET and WIDTH_OFFSET
        """
        node_center = [self.node_rect.left + self.node_rect.width / 2 + self.WIDTH_OFFSET,
                       self.node_rect.top + self.node_rect.height + self.HEIGHT_OFFSET]

        return node_center

    def set_n(self, n):
        """ Updates N """
        self.n = n
        self.alpha = 2.0 / (self.n + 1)

    def set_beta(self, beta):
        """ Updates beta """
        self.beta = beta

    def set_habitat_update_freq(self, update_freq):
        """ Updates habitat update frequency """
        self.update_freq = update_freq

    def set_shape(self, shape):
        """ Updates habitat shape """
        self.shape = shape

    def set_show_last_n_points(self, show_last_n_points):
        """ Updates if habitat should show its last N weighted points """
        if show_last_n_points == "True":
            self.show_last_n_points = True
        else:
            self.show_last_n_points = False


class Work(pg.sprite.Sprite):

    """
    Represents a work destination
    """
    #  [LEFT, RIGHT, TOP, BOTTOM]
    MARGINS = [70, 10, 10, 10]

    def __init__(self, image):
        # Call the parent class (Sprite) constructor
        pg.sprite.Sprite.__init__(self)

        self.image = image
        # self.mask = pg.mask.from_surface(self.image)
        self.rect = image.get_rect()

    def set_random_position(self):
        """ Sets workplace at random position """
        self.rect.center = get_random_position(self.MARGINS)

    def draw(self, surface):
        """ Draws workplace into surface """
        surface.blit(self.image, self.rect)


class Home(pg.sprite.Sprite):

    """
    Represents a home destination
    """
    #  [LEFT, RIGHT, TOP, BOTTOM]
    MARGINS = [10, 70, 10, 10]

    def __init__(self, image):
        # Call the parent class (Sprite) constructor
        pg.sprite.Sprite.__init__(self)

        self.image = image
        # self.mask = pg.mask.from_surface(self.image)
        self.rect = image.get_rect()

    def set_random_position(self):
        """ Sets home at random position """
        self.rect.center = get_random_position(self.MARGINS)

    def draw(self, surface):
        """ Draws home into surface """
        surface.blit(self.image, self.rect)


class AvoidablePlace(pg.sprite.Sprite):

    """
    Represents a home destination
    """
    #  [LEFT, RIGHT, TOP, BOTTOM]
    MARGINS = [40, 40, 10, 10]

    def __init__(self, image):
        # Call the parent class (Sprite) constructor
        pg.sprite.Sprite.__init__(self)

        self.image = image
        # self.mask = pg.mask.from_surface(self.image)
        self.rect = image.get_rect()

    def set_random_position(self):
        """ Sets home at random position """
        self.rect.center = get_random_position(self.MARGINS)

    def draw(self, surface):
        """ Draws home into surface """
        surface.blit(self.image, self.rect)


class Character(pg.sprite.Sprite):

    """ Represents the character of a node """

    DEFAULT_SPEED = 100
    DEFAULT_MOVEMENT = "automatic"
    UPDATE_COUNT = 2  # Every how many position changes update character movement iamge.
    INITIAL_RANDOM_POSIITON_MARGINS = [15, 15, 15, 15]
    STOP_FOR_A_WHILE_PROBABILITY = 1.0 / 50.0
    STOP_FOR_A_WHILE_TIME_INTERVAL = [5, 15]  # Seconds
    MINI_STOP_PROBABILITY = 1.0 / 10.0
    MINI_STOP_INTERVAL = [0, 3]  # Seconds

    AREA_CHANGE_PROBABILITY = 1.0 / 15.0
    HOME_AREA = [250, 250]
    WORK_AREA = [250, 250]

    def __init__(self, character_spritesheet, speed=DEFAULT_SPEED, movement=DEFAULT_MOVEMENT):
        # Call the parent class (Sprite) constructor
        pg.sprite.Sprite.__init__(self)

        # Load character facing the direction of the node
        self.character_spritesheet = character_spritesheet
        self.image = self.character_spritesheet.first()
        self.rect = self.image.get_rect()
        self.update_count = 0

        # Get random inital posiiton
        self.move = get_random_position(self.INITIAL_RANDOM_POSIITON_MARGINS)
        self.rect.center = self.move  # Set initial position
        self.speed = speed  # Node speed

        # Character movement image update frequency.
        # Means: update character movement every self.update_freq position changes.
        self.update_freq = self.UPDATE_COUNT
        self.update_count = 0

        # Character home and workplaces
        # Needed for random movement
        self.home_rect = None
        self.workplace_rect = None
        self.home_area = None
        self.workplace_area = None
        self.current_area = None
        self.areas = {"home": self.home_area, "workplace": self.workplace_area}
        self.wait_until = 0
        self.next_random_posiiton = None
        self.next_random_pos_rect = None
        self.center_float = None

        # Movement type
        self.movement = movement

        logging.debug("Created {0} node. Initial position ({1})".format(self.character_spritesheet, self.move))

    def set_home_rect(self, home_rect):
        """ Set home Rect and calculates its area """
        self.home_rect = home_rect
        self.home_area = pg.Rect(0, 0, self.HOME_AREA[0], self.HOME_AREA[1])
        self.home_area.center = home_rect.center
        self.areas["home"] = self.home_area

    def set_workplace_rect(self, worplace_rect):
        """ Set workplace Rect and calculates its area """
        self.workplace_rect = worplace_rect
        self.workplace_area = pg.Rect(0, 0, self.WORK_AREA[0], self.WORK_AREA[1])
        self.workplace_area.center = worplace_rect.center
        self.areas["workplace"] = self.workplace_area

    def draw(self, surface):
        """ Draws a chracter """
        surface.blit(self.image, self.rect)

    def update(self, screen_rect, keys, dt):
        """ Updates chracter position """
        if self.movement == "automatic":
            self.update_random_movement(dt)
        else:
            vector = [0, 0]
            for key in DIRECT_DICT:
                if keys[key]:
                    vector[0] += DIRECT_DICT[key][0]
                    vector[1] += DIRECT_DICT[key][1]
            self.update_char(vector)
            frame_speed = self.get_frame_speed(vector, dt)
            self.move[0] += vector[0] * frame_speed
            self.move[1] += vector[1] * frame_speed
            self.rect.center = self.move

        # Stop node of going off limits
        if not screen_rect.contains(self.rect):
            self.rect.clamp_ip(screen_rect)
            self.move = list(self.rect.center)

    def get_frame_speed(self, vector, dt):
        """ Get speed using dt to adjust speed to different frame rates """
        factor = (ANGLE_UNIT_SPEED if all(vector) else 1)
        frame_speed = self.speed * factor * dt

        return frame_speed

    def get_random_area(self):
        """ Random area: home or workplace"""
        if bool(random.getrandbits(1)):
            return "home"
        else:
            return "workplace"

    def get_random_position_in_current_area(self):
        """ Gets a random position inside the current area (workplace or home area) """
        random_position = [random.randint(self.areas[self.current_area].topleft[0],
                                          self.areas[self.current_area].topright[0]),
                           random.randint(self.areas[self.current_area].topleft[1],
                                          self.areas[self.current_area].bottomleft[1])]

        while not pg.display.get_surface().get_rect().collidepoint(random_position):
            random_position = [random.randint(self.areas[self.current_area].topleft[0],
                                              self.areas[self.current_area].topright[0]),
                               random.randint(self.areas[self.current_area].topleft[1],
                                              self.areas[self.current_area].bottomleft[1])]

        return random_position

    def normalize_vector(self, vector):
        """ Normalizes a vector to [(1|0), (1|0)]"""
        vector.normalize_ip()

        if vector[0] > 0.5:
            vector[0] = 1
        elif vector[0] < -0.5:
            vector[0] = -1
        else:
            vector[0] = 0

        if vector[1] > 0.5:
            vector[1] = 1
        elif vector[1] < -0.5:
            vector[1] = -1
        else:
            vector[1] = 0

        return vector

    def update_random_movement(self, dt):
        """ Calculates next random position """
        if not self.home_area or not self.workplace_area:
            return

        if not self.current_area:
            # Initia
            self.current_area = self.get_random_area()

            self.next_random_position = self.get_random_position_in_current_area()
            self.next_random_pos_rect = pg.Rect(0, 0, 50, 50)
            self.next_random_pos_rect.center = self.next_random_position

            logging.debug("[{0}] Next random posiiton: {1}".format(self.character_spritesheet,
                                                                   self.next_random_position))

            self.center_float = self.rect.center

        if self.wait_until:
            # If there is a wait_until value, do nothing until we have reached the timestamp
            if time.time() <= self.wait_until:
                pass
            else:
                self.wait_until = 0
        elif not self.next_random_pos_rect.collidepoint(self.rect.center):
            # If we have not arrived to the next random point update position towards it

            # Get direction vector
            direction_vector = pg.math.Vector2(self.next_random_position[0] - self.center_float[0],
                                               self.next_random_position[1] - self.center_float[1])

            # Normalize
            direction_vector = self.normalize_vector(direction_vector)
            self.update_char(direction_vector)

            # Update chracter position
            frame_speed = self.get_frame_speed(direction_vector, dt)
            self.move[0] = self.center_float[0] + direction_vector[0] * frame_speed
            self.move[1] = self.center_float[1] + direction_vector[1] * frame_speed

            self.center_float = self.move
            self.rect.center = self.move
        else:
            # Determine if we should stop for a while
            if random.randint(0, 1.0 / self.STOP_FOR_A_WHILE_PROBABILITY - 1) == 0:
                self.wait_until = time.time() + random.randint(self.STOP_FOR_A_WHILE_TIME_INTERVAL[0],
                                                               self.STOP_FOR_A_WHILE_TIME_INTERVAL[1])
            # Or if we should do a mini stop
            elif random.randint(0, 1.0 / self.MINI_STOP_PROBABILITY - 1) == 0:
                self.wait_until = time.time() + random.randint(self.MINI_STOP_INTERVAL[0],
                                                               self.MINI_STOP_INTERVAL[1])
            else:
                # Determine if we should change area
                if random.randint(0, 1.0 / self.AREA_CHANGE_PROBABILITY - 1) == 0:
                    if self.current_area == "home":
                        self.current_area = "workplace"
                    else:
                        self.current_area = "home"
                # Find random point in current area
                self.next_random_position = self.get_random_position_in_current_area()
                self.next_random_pos_rect = pg.Rect(0, 0, 50, 50)
                self.next_random_pos_rect.center = self.next_random_position

                logging.debug("[{0}] Next random posiiton: {1}".format(self.character_spritesheet,
                                                                       self.next_random_position))

    def update_char(self, direction_vector):
        """
        Updates character movement image.
        Only if character moves.
        """
        if direction_vector == [0, -1]:
            self.update_char_image(0)
        elif direction_vector == [1, -1]:
            self.update_char_image(1)
        elif direction_vector == [1, 0]:
            self.update_char_image(2)
        elif direction_vector == [1, 1]:
            self.update_char_image(3)
        elif direction_vector == [0, 1]:
            self.update_char_image(4)
        elif direction_vector == [-1, 1]:
            self.update_char_image(5)
        elif direction_vector == [-1, 0]:
            self.update_char_image(6)
        elif direction_vector == [-1, -1]:
            self.update_char_image(7)

    def update_char_image(self, direction):
        """ Update character image. """
        if self.update_count == self.update_freq:
            # Update node character movement
            self.character_spritesheet.set_direction(direction)
            self.image = self.character_spritesheet.next()

            self.update_count = 0
        else:
            self.update_count += 1

    def set_movement(self, movement):
        self.movement = movement


class Node(object):

    """
    Groups all the elemtns that represent a node and manages its update and drawing.
    """

    def __init__(self, character, home, workplace):
        self.character = character
        self.home = home
        self.workplace = workplace
        self.habitat = None
        self.habitat_update_thread = None

    def update(self, screen_rect, keys, dt):
        """ Update character position and movement """
        self.character.update(screen_rect, keys, dt)

    def draw(self, surface):
        """ Draw all components of a node"""
        if not self.habitat:
            # Create habitat first time that the node is draw so
            # it starts from the intial position of the node.
            self.habitat = Habitat(self.character.rect,
                                   color=self.character.character_spritesheet.color)
            self.habitat_update_thread = threading.Thread(target=self.habitat.update_thread)
            # Start habitat update thread
            self.habitat_update_thread.start()

        # Draw home / work
        if self.home:
            self.home.draw(surface)
        if self.workplace:
            self.workplace.draw(surface)

        # Draw habitat
        self.habitat.draw(surface)

        # Draw character
        self.character.draw(surface)


class Control(object):

    """ Controls demo scenario. """
    FPS = 60.0
    COLOR_ACTIVE_NODES = ('green', 'grey', 'red', 'yellow')

    HOME_SEPARATION_RATIO = 5
    WORK_SEPARATION_RATIO = 3

    DEFAULT_SEPARATION_RATIO = 2

    AVOIDABLE_PLACE_IMAGE = "data/disco.png"
    AVOIDABLE_PLACE_MARGINS = [15, 15, 15, 15]

    SELECTABLE_N = ('2', '5', '10', '15', '25', '50')
    SELECTABLE_BETA = ('1', '5', '10', '15', '25', '50')
    SELECTABLE_UPDATE_FREQS = ('0.1', '0.25', '0.5', '0.75', '1')
    SELECTABLE_SHAPES = ('Ellipse', 'Circle', 'Square', 'Rectangle')
    SELECTABLE_MOVEMENTS = ('automatic', 'manual')
    SELECTABLE_SHOW_LAST_N_POINTS = ('True', 'False')

    def __init__(self, options):
        os.environ['SDL_VIDEO_CENTERED'] = '1'  # Center screen
        pg.init()  # Init pygame
        if options.fullscreen:
            display_info = pg.display.Info()
            GlobalVars.SCREEN_SIZE[0] = display_info.current_w
            GlobalVars.SCREEN_SIZE[1] = display_info.current_h
            self.screen = pg.display.set_mode(GlobalVars.SCREEN_SIZE, pg.FULLSCREEN)
        else:
            self.screen = pg.display.set_mode(GlobalVars.SCREEN_SIZE)
        self.screen_rect = self.screen.get_rect()  # Get screen rectangle (so we know screen limits)
        self.clock = pg.time.Clock()  # Get pygame clock
        self.fps = Control.FPS  # Set frames per second

        # Get pressed keys
        self.keys = pg.key.get_pressed()

        # Demonstration nodes
        self.nodes = {}
        self.nodes_lock = threading.Lock()

        # Set background
        self._set_background()

        # Setup nodes
        self._setup_nodes()

        # Setup avoidable place
        self.avoidable_image = pg.image.load(os.path.abspath(self.AVOIDABLE_PLACE_IMAGE))
        self.avoidable_image.set_colorkey(pg.color.Color("white"))
        self.avoidable_place = AvoidablePlace(self.avoidable_image)
        self.avoidable_place.set_random_position()

        # Setup menu
        self._setup_menu()

    def _set_background(self):
        """ Set mosaic background """
        self.background = pg.Surface((self.screen_rect.width, self.screen_rect.height))
        self.background.fill((0, 0, 0))

        temp = pg.image.load(os.path.abspath("data/grass4.jpg")).convert()
        width = temp.get_width()
        height = temp.get_height()

        dif_h = float(self.screen_rect.height) / height
        dif_h = int(math.ceil(dif_h))
        dif_w = float(self.screen_rect.width) / width
        dif_w = int(math.ceil(dif_w))

        if dif_h < 1:
            dif_h = 1

        if dif_w < 1:
            dif_w = 1

        # Fill all background with the mosaic of background file
        for iterator1 in range(dif_h):
            for iterator2 in range(dif_w):
                self.background.blit(temp, (iterator2 * width, iterator1 * height))

    def _setup_menu(self):
        """ Initializes the top menubar """
        # Initialize menu
        ms.init()

        # Set colors
        ms.BGCOLOR = pg.color.Color("black")
        ms.FGCOLOR = pg.color.Color(200, 200, 200, 255)
        ms.BGHIGHTLIGHT = pg.color.Color(100, 100, 100, 180)
        ms.BORDER_HL = pg.color.Color(200, 200, 200, 180)

        # Create menu
        n = ms.Menu('N', self.SELECTABLE_N)
        beta = ms.Menu("BETA", self.SELECTABLE_BETA)
        freq = ms.Menu('UPDATE FREQ.', self.SELECTABLE_UPDATE_FREQS)
        shape = ms.Menu('SHAPE', self.SELECTABLE_SHAPES)
        show_last_n_points = ms.Menu('SHOW LAST N POINTS', self.SELECTABLE_SHOW_LAST_N_POINTS)
        movements = ms.Menu('MOVEMENT', self.SELECTABLE_MOVEMENTS)
        self.bar = ms.MenuBar()
        options = []
        # Add a menu option for each active node
        for color in self.COLOR_ACTIVE_NODES:
            options.append(ms.Menu(color.upper(), (n, beta, freq, shape, show_last_n_points, movements)))
        # Add a menu option for all active nodes
        options.append(ms.Menu('ALL', (n, beta, freq, shape, show_last_n_points, "RESET")))
        # Set up bar
        self.bar.set(options)

    def _setup_nodes(self):
        """ Initializes all the active ndoes and its components """
        self.nodes_lock.acquire()
        for color in self.COLOR_ACTIVE_NODES:

            # Create character
            mario = Mario(color=color)
            character = Character(mario)

            # Extract home image from character
            home = Home(mario.home_image)

            # Extract workplace image from character
            workplace = Work(mario.workplace_image)

            # Create node
            node = Node(character, home, workplace)

            self.nodes[color] = node

        # Randomly positioning all node elements
        self._random_node_positioning()
        self.nodes_lock.release()

    def _random_node_positioning(self):
        """ Position homes and workplaces """
        # Position homes
        while True:
            for node in self.nodes.itervalues():
                node.home.set_random_position()
                logging.debug("Trying to position {0} home at {1}".format(node.character.character_spritesheet,
                                                                          node.home.rect))
                failed = False
                tried = 0
                while self._home_work_collision(node.home, self.HOME_SEPARATION_RATIO):
                    logging.debug("Collision detected.")
                    node.home.set_random_position()
                    logging.debug("Trying to position {0} home at {1}".format(node.character.character_spritesheet,
                                                                              node.home.rect))
                    tried += 1
                    if tried == 10:
                        failed = True
                        break
                if failed:
                    break
                else:
                    node.character.set_home_rect(node.home.rect)
            if failed:
                logging.debug("Positioning of {0} home failed.".format(node.character.character_spritesheet))
                # Start again
                for node in self.nodes.itervalues():
                    node.home.rect.center = (-self.screen_rect.width, -self.screen_rect.height)
            else:
                break

        # Position workplaces
        while True:
            for node in self.nodes.itervalues():
                node.workplace.set_random_position()
                logging.debug("Trying to position {0} workplace at {1}".format(node.character.character_spritesheet,
                                                                               node.workplace.rect))
                failed = False
                tried = 0
                while self._home_work_collision(node.workplace, self.WORK_SEPARATION_RATIO):
                    logging.debug("Collision detected.")
                    node.workplace.set_random_position()
                    logging.debug("Trying to position {0} workplace at {1}".format(node.character.character_spritesheet,
                                                                                   node.workplace.rect))
                    tried += 1
                    if tried == 10:
                        failed = True
                        break
                if failed:
                    break
                else:
                    node.character.set_workplace_rect(node.workplace.rect)
            if failed:
                logging.debug("Positioning of {0} workplace failed.".format(node.character.character_spritesheet))
                # Start again
                for node in self.nodes.itervalues():
                    node.workplace.rect.center = (-self.screen_rect.width, -self.screen_rect.height)
            else:
                break

    def _home_work_collision(self, sprite, ratio=DEFAULT_SEPARATION_RATIO):
        """ Check if sprite collides with any other elemnt of the demo """
        collide_function = pg.sprite.collide_rect_ratio(ratio)

        for node in self.nodes.itervalues():
            if sprite is not node.workplace and collide_function(sprite, node.workplace):
                logging.debug("Workplace collision")
                return True

            if sprite is not node.home and collide_function(sprite, node.home):
                logging.debug("Home collision")
                return True

        return False

    def _update_nodes(self, choice):
        """
        Updates representation of nodes based on a menu action. A choice is an array with the format:
        [("MENU_POSIITON", "MENU_TAG"), ("SUBMENU_POSITION","SUBMENU_TAG"), (...)]
        """
        # Top menu (selects node(s))
        target = choice[0][1].lower()

        # 1 submenu (property)
        submenu1 = choice[1][1].lower()

        if target == 'all':
            if submenu1 == "reset":
                # Remove nodes
                self.nodes_lock.acquire()
                for node in self.nodes.itervalues():
                    # Stop habitat updating thread
                    node.habitat.killed = True
                self.nodes.clear()
                self.nodes_lock.release()
                # Setup nodes again
                self._setup_nodes()

            for node in self.nodes.itervalues():
                if submenu1 == 'n':
                    node.habitat.set_n(int(choice[2][1]))
                if submenu1 == 'beta':
                    node.habitat.set_beta(int(choice[2][1]))
                elif submenu1 == 'update freq.':
                    node.habitat.set_habitat_update_freq(float(choice[2][1]))
                elif submenu1 == 'shape':
                    node.habitat.set_shape(choice[2][1].lower())
                elif submenu1 == 'show last n points':
                    node.habitat.set_show_last_n_points(choice[2][1])

        else:
            if submenu1 == 'n':
                self.nodes[target].habitat.set_n(int(choice[2][1]))
            if submenu1 == 'beta':
                self.nodes[target].habitat.set_beta(int(choice[2][1]))
            elif submenu1 == 'update freq.':
                self.nodes[target].habitat.set_habitat_update_freq(float(choice[2][1]))
            elif submenu1 == 'shape':
                self.nodes[target].habitat.set_shape(choice[2][1].lower())
            elif submenu1 == 'show last n points':
                self.nodes[target].habitat.set_show_last_n_points(choice[2][1])
            elif submenu1 == 'movement':
                self.nodes[target].character.set_movement(choice[2][1])

    def event_loop(self):
        """ One event loop. """
        self.keys = pg.key.get_pressed()
        for event in pg.event.get():
            # Check if user QUITS (Escapes or clase the demo window)
            if event.type == pg.QUIT or self.keys[pg.K_ESCAPE]:
                GlobalVars.RUNNING = False

            # Pass event to MenuBar to update the Menu
            self.bar.update(event)
            if self.bar.choice:
                self._update_nodes(self.bar.choice)

    def main_loop(self):
        """ Main game loop. """
        while GlobalVars.RUNNING:
            try:
                # Clear screen
                self.screen.blit(self.background, (0, 0))
                # self.screen.fill(pg.color.Color("white"))

                # Check for events
                self.event_loop()

                # Draw avoidable place
                self.avoidable_place.draw(self.screen)

                # Update and draw all elements of the demonstration
                time_delta = self.clock.tick(self.fps) / 1000.0
                self.nodes_lock.acquire()
                for node in self.nodes.itervalues():
                    # Delta time (needed to keep the same movement speed with different framerates)
                    node.update(self.screen_rect, self.keys, time_delta)
                    node.draw(self.screen)
                self.nodes_lock.release()

                # Draw menu
                self.bar.draw()
                # Iterate over all active Menu items and draw them
                for bar in self.bar:
                    bar.draw()

                # Update display
                pg.display.flip()
            except Exception:
                traceback.print_exc()
                # Any exception will terminate the simulation gracefully
                return


# Notifies threads to stop
def signal_handler(sig, frame):
    """
    Handler executed when a signal is catched
    :param sig: Signal number
    :param frame: Current stack frame
    """
    GlobalVars.RUNNING = False


def main():
    # Parse arguments
    parser = argparse.ArgumentParser("PrivHab demonstration")
    parser.add_argument('--debug', '-d',
                        help='print debug information.',
                        action='store_true')
    parser.add_argument('--fullscreen', '-f',
                        help='Fullscreen mode.',
                        action='store_true')
    options = parser.parse_args()

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Set debug
    if options.debug:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

    # Start demo
    run_it = Control(options)
    run_it.main_loop()

    # EXit gracefullt
    GlobalVars.RUNNING = False
    pg.quit()
    sys.exit()

# Main function
if __name__ == "__main__":
    main()
