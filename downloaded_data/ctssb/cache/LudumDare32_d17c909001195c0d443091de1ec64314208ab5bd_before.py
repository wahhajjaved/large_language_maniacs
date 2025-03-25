import pygame

"""
Monitors the users mouse and their selections
"""
class PickingHandler(object):
    SUCCESS_COLOR = (0,0,255)
    ERROR_COLOR = (255,0,0)

    def __init__(self, transmutation_manager, physics_manager):
        self.transmutation_manager = transmutation_manager
        self.physics_manager = physics_manager
        self._user_selection_bound1 = None
        self._user_selection_bound2 = None

    def is_picked(self, actor, position):
        return actor.get_rect().collidepoint(position)

    def tile_at_point(self, position, tile_size):
        return (int(position[0] / tile_size), int(position[1] / tile_size))

    def start_user_selection(self, position, tile_size):
        self._user_selection_bound1 = self.tile_at_point(position, tile_size)

    def stop_user_selection(self):
        if self._user_selection_bounds is not None:
            pygame.event.post(pygame.event.Event(pygame.USEREVENT, {"bounds":self._user_selection_bounds}))
        self._user_selection_bound1 = None
        self._user_selection_bound2 = None

    @property
    def surface(self):
        if self._user_selection_bound1 is not None:
            return self.selection_surface
        else:
            return pygame.Surface((0,0))

    @property
    def position(self):
        if self._user_selection_bound1 is not None:
            return self._user_selection_position
        else:
            return (0,0)

    def _is_selection_space_filled(self, tile_size):
        px_selection_box = self.selection_surface.get_rect().move(self._user_selection_position)
        tile_selection_box = pygame.Rect(px_selection_box.left / tile_size, px_selection_box.top / tile_size, px_selection_box.width / tile_size, px_selection_box.height / tile_size)
        return self.physics_manager.is_space_filled(tile_selection_box)

    def get_points_used(self, tile_size):
        return self.transmutation_manager.get_points_required((self.selection_surface.get_width() / tile_size), (self.selection_surface.get_height() / tile_size))

    def update(self, delta, tile_size):
        if self._user_selection_bound1 is not None: #user can select right now
            new_bound2 = self.tile_at_point(pygame.mouse.get_pos(), tile_size)
            if new_bound2 != self._user_selection_bound2:
                self._user_selection_bound2 = new_bound2
                self._user_selection_position = (
                    min(self._user_selection_bound1[0], self._user_selection_bound2[0]) * tile_size,
                    min(self._user_selection_bound1[1], self._user_selection_bound2[1]) * tile_size
                )
                self.selection_surface = pygame.Surface((
                    abs(self._user_selection_bound2[0] - self._user_selection_bound1[0]) * tile_size,
                    abs(self._user_selection_bound2[1] - self._user_selection_bound1[1]) * tile_size
                    ))
                self.selection_surface.set_alpha(150)
            if self.get_points_used(tile_size) > self.transmutation_manager.current_points or self._is_selection_space_filled(tile_size):
                self.selection_surface.fill(PickingHandler.ERROR_COLOR)
                self._user_selection_bounds = None
            else:
                self.selection_surface.fill(PickingHandler.SUCCESS_COLOR)
                self._user_selection_bounds = self.selection_surface.get_rect().move(self._user_selection_position)
