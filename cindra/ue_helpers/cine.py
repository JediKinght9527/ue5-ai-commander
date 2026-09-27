"""ue_helpers.cine —— Sequencer + Movie Render Queue 原语 (真 UE 注入源)。

设计要点:
- 关键帧数学在 cindra 侧 (camera_math) 算好, 这里只往 9 个 transform 通道写
  纯数字 —— 双后端消费同一份 key 数组。
- cnd_seq_render 用 MRQ + PIE executor, 发射即返回 pending; executor 存模块
  全局防 GC (MRQ 脚本化的经典坑); 渲前先存脏包 (未存关卡是 MRQ 头号失败原因)。
- 帧序列落盘 <Project>/Saved/Cindra/renders/<seq>/, cindra 侧轮询帧数稳定。
"""

SOURCE = r"""
import json
import os
import unreal

_SEQ_DIR = "/Game/Cindra/Sequences"
_MRQ_EXECUTOR = {"ref": None}  # 防 GC


def _seq_path(name):
    return "%s/%s.%s" % (_SEQ_DIR, name, name)


def _load_seq(name):
    return unreal.load_asset(_seq_path(name))


def _find_actor_by_label(label):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def cnd_seq_create(name, fps=24, seconds=8.0):
    if _load_seq(name):
        return json.dumps({"ok": False, "error": "sequence exists: %s" % name})
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    seq = tools.create_asset(name, _SEQ_DIR, unreal.LevelSequence,
                             unreal.LevelSequenceFactoryNew())
    if seq is None:
        return json.dumps({"ok": False, "error": "create_asset failed"})
    fps = int(fps)
    total = int(round(fps * float(seconds)))
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(total)
    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return json.dumps({"ok": True, "action": "seq_create", "name": name,
                       "fps": fps, "end_frame": total,
                       "asset": _seq_path(name)})


def cnd_seq_add_camera(sequence, camera_name=None):
    seq = _load_seq(sequence)
    if seq is None:
        return json.dumps({"ok": False, "error": "no sequence: %s" % sequence})
    cam_label = camera_name or ("CineCam_%d" % (len(seq.get_bindings()) + 1))
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    with unreal.ScopedEditorTransaction("Cindra AddCineCamera"):
        cam = eas.spawn_actor_from_class(
            unreal.CineCameraActor, unreal.Vector(0, 0, 300),
            unreal.Rotator(0, 0, 0))
        cam.set_actor_label(cam_label)
        binding = seq.add_possessable(cam)
        track = binding.add_track(unreal.MovieScene3DTransformTrack)
        section = track.add_section()
        section.set_range(seq.get_playback_start(), seq.get_playback_end())
        # 默认给整段一个 camera cut (可被 cnd_seq_add_cut 覆盖细分)
        cut_tracks = seq.find_tracks_by_type(unreal.MovieSceneCameraCutTrack)
        cut_track = (cut_tracks[0] if cut_tracks
                     else seq.add_track(unreal.MovieSceneCameraCutTrack))
        cut = cut_track.add_section()
        cut.set_range(seq.get_playback_start(), seq.get_playback_end())
        cam_id = seq.make_binding_id(binding,
                                     unreal.MovieSceneObjectBindingSpace.LOCAL)
        cut.set_camera_binding_id(cam_id)
    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return json.dumps({"ok": True, "action": "seq_add_camera",
                       "sequence": sequence, "camera": cam_label})


def _find_binding(seq, label):
    for b in seq.get_bindings():
        if b.get_display_name() == label or b.get_name() == label:
            return b
    return None


def cnd_seq_add_keys(sequence, camera, keys):
    seq = _load_seq(sequence)
    if seq is None:
        return json.dumps({"ok": False, "error": "no sequence: %s" % sequence})
    binding = _find_binding(seq, camera)
    if binding is None:
        return json.dumps({"ok": False, "error": "no camera: %s" % camera})
    tracks = [t for t in binding.get_tracks()
              if isinstance(t, unreal.MovieScene3DTransformTrack)]
    if not tracks:
        return json.dumps({"ok": False, "error": "no transform track"})
    section = tracks[0].get_sections()[0]
    channels = section.get_all_channels()  # 9: loc xyz, rot xyz, scale xyz
    with unreal.ScopedEditorTransaction("Cindra SeqKeys"):
        for k in keys:
            frame = unreal.FrameNumber(int(k["frame"]))
            loc = k["location"]
            rot = k["rotation"]  # (pitch, yaw, roll) -> UE 通道序 roll,pitch,yaw
            vals = [loc[0], loc[1], loc[2], rot[2], rot[0], rot[1],
                    1.0, 1.0, 1.0]
            for ch, v in zip(channels[:9], vals):
                ch.add_key(frame, float(v))
    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return json.dumps({"ok": True, "action": "seq_add_keys",
                       "sequence": sequence, "camera": camera,
                       "total_keys": len(keys)})


def cnd_seq_add_cut(sequence, camera, start_frame=None, end_frame=None):
    seq = _load_seq(sequence)
    if seq is None:
        return json.dumps({"ok": False, "error": "no sequence: %s" % sequence})
    binding = _find_binding(seq, camera)
    if binding is None:
        return json.dumps({"ok": False, "error": "no camera: %s" % camera})
    start = int(start_frame or 0)
    end = int(end_frame if end_frame is not None else seq.get_playback_end())
    cut_tracks = seq.find_tracks_by_type(unreal.MovieSceneCameraCutTrack)
    cut_track = (cut_tracks[0] if cut_tracks
                 else seq.add_track(unreal.MovieSceneCameraCutTrack))
    with unreal.ScopedEditorTransaction("Cindra SeqCut"):
        cut = cut_track.add_section()
        cut.set_range(start, end)
        cam_id = seq.make_binding_id(binding,
                                     unreal.MovieSceneObjectBindingSpace.LOCAL)
        cut.set_camera_binding_id(cam_id)
    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return json.dumps({"ok": True, "action": "seq_add_cut",
                       "sequence": sequence, "camera": camera,
                       "start": start, "end": end})


def cnd_seq_list(sequence=None):
    if sequence is None:
        reg = unreal.AssetRegistryHelpers.get_asset_registry()
        names = [str(a.asset_name) for a in
                 reg.get_assets_by_path(unreal.Name(_SEQ_DIR))]
        return json.dumps({"ok": True, "action": "seq_list",
                           "sequences": sorted(names)})
    seq = _load_seq(sequence)
    if seq is None:
        return json.dumps({"ok": False, "error": "no sequence: %s" % sequence})
    cams = {}
    for b in seq.get_bindings():
        n = 0
        for t in b.get_tracks():
            if isinstance(t, unreal.MovieScene3DTransformTrack):
                for s in t.get_sections():
                    chans = s.get_all_channels()
                    n = max(n, chans[0].get_num_keys() if chans else 0)
        cams[str(b.get_display_name())] = {"keys": n}
    return json.dumps({"ok": True, "action": "seq_list", "name": sequence,
                       "fps": int(seq.get_display_rate().numerator),
                       "end_frame": int(seq.get_playback_end()),
                       "cameras": cams})


def cnd_seq_render(sequence, out_dir=None, res=(1280, 720), samples=None):
    seq = _load_seq(sequence)
    if seq is None:
        return json.dumps({"ok": False, "error": "no sequence: %s" % sequence})
    # 未存关卡是 MRQ 脚本化的头号失败原因 —— 渲前先存
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    proj = unreal.SystemLibrary.get_project_saved_directory()
    out = out_dir or os.path.join(proj, "Cindra", "renders", sequence)
    os.makedirs(out, exist_ok=True)

    subsystem = unreal.get_editor_subsystem(
        unreal.MoviePipelineQueueSubsystem)
    queue = subsystem.get_queue()
    queue.delete_all_jobs()
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.sequence = unreal.SoftObjectPath(_seq_path(sequence))
    world = unreal.get_editor_subsystem(
        unreal.UnrealEditorSubsystem).get_editor_world()
    job.map = unreal.SoftObjectPath(world.get_path_name())
    config = job.get_configuration()
    out_setting = config.find_or_add_setting_by_class(
        unreal.MoviePipelineOutputSetting)
    out_setting.output_directory = unreal.DirectoryPath(out)
    out_setting.file_name_format = "frame_{frame_number}"
    out_setting.output_resolution = unreal.IntPoint(int(res[0]), int(res[1]))
    config.find_or_add_setting_by_class(
        unreal.MoviePipelineImageSequenceOutput_PNG)
    config.find_or_add_setting_by_class(
        unreal.MoviePipelineDeferredPassBase)
    executor = unreal.MoviePipelinePIEExecutor()
    _MRQ_EXECUTOR["ref"] = executor  # 防 GC
    subsystem.render_queue_with_executor_instance(executor)
    return json.dumps({"ok": True, "action": "seq_render", "pending": True,
                       "sequence": sequence, "out_dir": out,
                       "expected_frames": int(seq.get_playback_end())})
"""
