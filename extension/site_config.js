// Shared site configuration for BambiBrowser content scripts and popup.
const BAMBI_DEFAULT_SITES = [
  {
    id: "hypnotube",
    label: "Hypnotube",
    enabled: true,
    hosts: ["hypnotube.com", "*.hypnotube.com"],
    detector: "hypnotube",
  },
  {
    id: "bambicloud",
    label: "BambiCloud",
    enabled: true,
    hosts: ["bambicloud.com", "*.bambicloud.com"],
    detector: "bambicloud",
  },
];

function bambiDefaultSites() {
  return BAMBI_DEFAULT_SITES.map(site => ({ ...site, hosts: [...site.hosts] }));
}
