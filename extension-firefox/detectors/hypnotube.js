// HypnoTube detector
window.BambiDetectors = window.BambiDetectors || {};

window.BambiDetectors.hypnotube = {
  name: 'hypnotube',
  
  findVideo: function() {
    const videos = document.querySelectorAll("video");
    let best = null;
    let maxArea = 0;
    
    for (const v of videos) {
      const src = v.currentSrc || v.src;
      if (!src || src.startsWith('blob:')) continue;
      
      const isHypno = src.includes("media.hypnotube.com");
      const rect = v.getBoundingClientRect();
      const area = rect.width * rect.height;
      const score = isHypno ? area * 2 : area;
      
      if (score > maxArea) {
        maxArea = score;
        best = v;
      }
    }
    
    return best;
  },
  
  getVideoUrl: function(video) {
    return video.currentSrc || video.src;
  }
};