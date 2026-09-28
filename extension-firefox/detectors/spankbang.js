// SpankBang detector
window.BambiDetectors = window.BambiDetectors || {};

window.BambiDetectors.spankbang = {
  name: 'spankbang',
  
  findVideo: function() {
    // SpankBang specific video detection
    const video = document.querySelector("video#main_video");
    return video || document.querySelector("video");
  },
  
  getVideoUrl: function(video) {
    return video?.currentSrc || video?.src;
  }
};