"use strict";
$(() => {
    // Some sanity checks that can't be used

    // Firefox doesn't allow this
    // Misc.preventExtensions(document);

    // Chrome extensions rely on window being extensible
    // Misc.preventExtensions(window);

    // Make the player
    window.p = new Player({
        $container: $("#player"),
        videoSrc: window.video.location,
        videoId: window.video.id,
        videoStart: window.video.start_time,
        videoEnd: window.video.end_time,
        isImageSequence: window.video.is_image_sequence,
        turkMetadata: window.video.turk_task,
    });
    var view = window.p.view;
    view.scaleToFit = $('#scale-checkbox')[0].checked;
    view.$('video').css({
            height: `100%`,
            'flex-grow': 1
    });
    view.video.fit();
    view.sizeVideoFrame();
});
