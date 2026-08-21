// Bambicloud detector
window.BambiDetectors = window.BambiDetectors || {};

window.BambiDetectors.bambicloud = {
  name: 'bambicloud',

  findVideo: function() {
    return null;
  },

  getVideoUrl: function(video) {
    return null;
  },

  handleSpecialPage: function() {
    const url = window.location.href;

    try {
      const urlObj = new URL(url);

      // First check if we're actually on bambicloud.com
      if (!urlObj.hostname.includes('bambicloud.com')) {
        return { isSpecial: false };
      }

      const pathname = urlObj.pathname;

      // Direct Audio File URL (e.g., cdn.bambicloud.com/uuid.mp3)
      const audioMatch = pathname.match(/\.(mp3|wav|ogg|m4a|aac|flac|opus)$/i);
      if (audioMatch) {
        const uuidMatch = url.match(/[0-9a-f\-]{8}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{12}/);
        const uuid = uuidMatch ? uuidMatch[0] : null;
        return {
          isSpecial: true,
          type: 'direct',
          uuid: uuid,
          url: url,
          audioOnly: true
        };
      }

      // File URL pattern: /file/[uuid]
      const fileMatch = pathname.match(/^\/file\/[0-9a-f\-]+$/);
      // Playlist URL pattern: /playlist/[uuid]
      const playlistMatch = pathname.match(/^\/playlist\/[0-9a-f\-]+$/);

      if (fileMatch || playlistMatch) {
        const uuidMatch = url.match(/[0-9a-f\-]{8}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{4}-[0-9a-f\-]{12}/);
        const uuid = uuidMatch ? uuidMatch[0] : null;

        const params = new URLSearchParams(urlObj.search);
        const visualSession = params.get('visual') === 'true' ||
                             params.get('mode') === 'visual' ||
                             document.querySelector('[data-visual-session]');

        const audioOnly = params.get('audio') === 'true' ||
                         params.get('mode') === 'audio' ||
                         Boolean(document.querySelector('[data-audio-only]')) ||
                         true;

        return {
          isSpecial: true,
          type: fileMatch ? 'file' : 'playlist',
          uuid: uuid,
          visualSession: visualSession,
          audioOnly: audioOnly,
          url: url
        };
      }
    } catch (e) {
      console.error('[Bambi] Error parsing URL for bambicloud detection:', e);
    }

    return { isSpecial: false };
  }
};