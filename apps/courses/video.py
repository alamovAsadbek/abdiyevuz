"""Yuklangan videoni siqish va shifrlangan HLS (AES-128) ga o'tkazish.
Sifat deyarli yo'qolmaydi (x264 CRF 27), hajm odatda 2-5 baravar kamayadi. Asl fayl o'chiriladi."""
import logging
import os
import shutil
import subprocess
import threading

from django.conf import settings

log = logging.getLogger(__name__)
_sem = threading.Semaphore(settings.VIDEO_WORKERS)


def hls_dir(lesson_id):
    return settings.PRIVATE_ROOT / "hls" / str(lesson_id)


def probe_duration(path):
    try:
        out = subprocess.run([settings.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=60)
        return int(float(out.stdout.strip() or 0))
    except Exception:
        return 0


def start(lesson_id):
    threading.Thread(target=process, args=(lesson_id,), daemon=True, name=f"video-{lesson_id}").start()


def process(lesson_id):
    from .models import LessonModel
    with _sem:
        lesson = LessonModel.objects.filter(pk=lesson_id).first()
        if not lesson or not lesson.video_src:
            return
        src = lesson.video_src.path
        out = hls_dir(lesson_id)
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        try:
            key = os.urandom(16)
            (out / "enc.key").write_bytes(key)
            (out / "enc.keyinfo").write_text(f"/stream/{lesson_id}/key/\n{out / 'enc.key'}\n{os.urandom(16).hex()}\n")
            cmd = [settings.FFMPEG, "-y", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", str(settings.VIDEO_CRF), "-pix_fmt", "yuv420p",
                   "-vf", f"scale=-2:'min({settings.VIDEO_MAX_HEIGHT},ih)'",
                   "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-sn", "-dn",
                   "-f", "hls", "-hls_time", "6", "-hls_playlist_type", "vod", "-hls_flags", "independent_segments",
                   "-hls_key_info_file", str(out / "enc.keyinfo"),
                   "-hls_segment_filename", str(out / "seg%05d.ts"), str(out / "index.m3u8")]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not (out / "index.m3u8").exists():
                raise RuntimeError((r.stderr or "ffmpeg xatosi")[-280:])
            before = os.path.getsize(src)
            after = sum(f.stat().st_size for f in out.glob("seg*.ts"))
            dur = probe_duration(src)
            lesson.video_src.delete(save=False)
            LessonModel.objects.filter(pk=lesson_id).update(hls_status="ready", hls_error="", duration=dur,
                                                            size_before=before, size_after=after, video_src="")
            log.info("Video tayyor #%s: %.1f MB -> %.1f MB", lesson_id, before / 1e6, after / 1e6)
        except Exception as e:  # noqa
            log.exception("Video qayta ishlashda xato")
            LessonModel.objects.filter(pk=lesson_id).update(hls_status="failed", hls_error=str(e)[:290])
        finally:
            from apps.notifications.services import notify_staff
            l2 = LessonModel.objects.filter(pk=lesson_id).first()
            if l2:
                notify_staff("courses", f"“{l2.title}” videosi: " + ("tayyor" if l2.hls_status == "ready" else "qayta ishlashda xatolik"),
                             f"/lessons/{lesson_id}/")
