from pathlib import Path
import pyglet
pyglet.options['audio'] = ('openal', 'pulse', 'directsound', 'silent')
from pyglet.media import Player, StaticSource, load

import moderngl
import moderngl_window
from moderngl_window.scene import KeyboardCamera
from moderngl_window import geometry
from moderngl_window import settings

from beatsaber import RESOURCE_DIR as DEFAULT_RESOURCE_DIR
from beatsaber.track import BSTrack
from beatsaber.scene import BSScene
from beatsaber.input import HandTracker


class BeatSaber(moderngl_window.WindowConfig):
    title = "Beat Saber Light Show"
    window_size = 1920, 1080
    cursor = False
    aspect_ratio = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.wnd.mouse_exclusivity = False
        self.camera = KeyboardCamera(self.wnd.keys, aspect_ratio=self.wnd.aspect_ratio, fov=60, near=1.0, far=1000.0)
        self.camera.velocity = 50
        self.camera_enabled = False

        print("Song  :", self.argv.song)
        print("Info  :", self.argv.info)
        print("Track :", self.argv.track)

        resource_dir = DEFAULT_RESOURCE_DIR
        if self.argv.song is not None:
            resource_dir = Path.cwd()
            settings.DATA_DIRS.insert(0, resource_dir)
            print("Resource dir:", resource_dir)

        dat_file = self.argv.info or 'megalovania_remix/info.dat'
        song_file = self.argv.song or 'megalovania_remix/song.wav'
        track_file = self.argv.track or 'megalovania_remix/Expert.dat'

        # Validate required files exist
        song_path = resource_dir / song_file
        if not song_path.exists():
            raise FileNotFoundError(f"Song file not found: {song_path}")

        track_path = resource_dir / track_file
        if not track_path.exists():
            raise FileNotFoundError(f"Track file not found: {track_path}")

        meta = self.load_json(dat_file)
        self.scene = BSScene(
            self.load_scene('bs_map3.glb'),
            self.camera,
            BSTrack(track_file, meta['_beatsPerMinute']),
        )

        self.quad_fs = geometry.quad_fs()

        # Postprocess programs
        self.copy_prog = self.load_program('programs/copy.glsl')
        self.copy_greyscale_prog = self.load_program('programs/copy_greyscale.glsl')
        self.blur_h_prog = self.load_program('programs/blur_h.glsl')
        self.blur_v_prog = self.load_program('programs/blur_v.glsl')
        self.combine = self.load_program('programs/combine.glsl')
        self.combine['texture1'] = 1

        # blur stuff
        self.offscreen_texture = self.ctx.texture((self.wnd.buffer_width, self.wnd.buffer_height), 4)
        self.offscreen_depth = self.ctx.depth_texture((self.wnd.buffer_width, self.wnd.buffer_height))
        self.offscreen = self.ctx.framebuffer(
            color_attachments=[self.offscreen_texture],
            depth_attachment=self.offscreen_depth,
        )
        bd = 4
        self.blur_h_texture = self.ctx.texture((self.wnd.buffer_width // bd, self.wnd.buffer_height // bd), 4)
        self.blur_h_texture.repeat_x = False
        self.blur_h_texture.repeat_y = False
        self.blur_h = self.ctx.framebuffer(color_attachments=[self.blur_h_texture])
        self.blur_v_texture = self.ctx.texture((self.wnd.buffer_width // bd, self.wnd.buffer_height // bd), 4)
        self.blur_v_texture.repeat_x = False
        self.blur_v_texture.repeat_y = False
        self.blur_v = self.ctx.framebuffer(color_attachments=[self.blur_v_texture])

        self.music_player = Player()
        self.music_source = StaticSource(load(song_path))
        self.music_player.queue(self.music_source)
        self.music_player.play()
        # self.music_player.seek(60.0 * 3)
        self.music_player.volume = 1.0
        pyglet.clock.tick()

        # Hand tracking for sabers
        self.hand_tracker = HandTracker()
        if self.hand_tracker.available:
            print("Initializing hand tracking...")
            self.hand_tracker.start()
        else:
            print("Hand tracking not available (install mediapipe opencv-python)")

    def render(self, time, frame_time):
        pyglet.clock.tick()
        self.offscreen.clear()
        self.blur_h.clear()
        self.blur_v.clear()
        time = self.music_player.time

        self.offscreen.use()
        self.ctx.enable_only(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.scene.render(self.camera, time, frame_time)

        # Render hand-tracked sabers
        left_hand, right_hand = self.hand_tracker.get_hand_positions()
        if left_hand or right_hand:
            self.scene.render_sabers(self.camera, left_hand, right_hand)

        self.ctx.enable_only(moderngl.NOTHING)

        self.blur_v.use()
        self.offscreen_texture.use(location=0)
        self.quad_fs.render(self.copy_prog)
        self.blur_v_texture.build_mipmaps(max_level=10)

        self.blur_h.use()
        self.blur_v_texture.use(location=0)
        self.quad_fs.render(self.blur_h_prog)
        self.blur_h_texture.build_mipmaps(max_level=10)

        self.blur_v.use()
        self.blur_h_texture.use(location=0)
        self.quad_fs.render(self.blur_v_prog)

        # Back to screen
        self.wnd.fbo.use()
        self.offscreen_texture.use(location=0)
        self.blur_v_texture.use(location=1)
        self.quad_fs.render(self.combine)

    def key_event(self, key, action, modifiers):
        keys = self.wnd.keys

        if self.camera_enabled:
            self.camera.key_input(key, action, modifiers)

        if action == keys.ACTION_PRESS:
            if key == keys.C:
                self.camera_enabled = not self.camera_enabled
                self.wnd.mouse_exclusivity = self.camera_enabled
                self.wnd.cursor = not self.camera_enabled
            elif key == keys.SPACE:
                self.timer.toggle_pause()
                if self.music_player.playing:
                    self.music_player.pause()
                else:
                    self.music_player.play()
            elif key == keys.LEFT:
                self.music_player.seek(max(0, self.music_player.time - 10))
            elif key == keys.RIGHT:
                self.music_player.seek(self.music_player.time + 10)

    def mouse_position_event(self, x: int, y: int, dx, dy):
        if self.camera_enabled:
            self.camera.rot_state(-dx, -dy)

    def resize(self, width: int, height: int):
        self.camera.projection.update(aspect_ratio=self.wnd.aspect_ratio)
        self.scene.resize()

    def close(self):
        """Clean up resources when closing."""
        if self.hand_tracker:
            self.hand_tracker.stop()

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--song', type=str, help="Song file")
        parser.add_argument('--info', type=str, help="Info file")
        parser.add_argument('--track', type=str, help="Track file")




def run_from_cmd():
    moderngl_window.run_window_config(BeatSaber)


if __name__ == '__main__':
    run_from_cmd()
