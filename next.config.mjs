import nextra from "nextra";

const withNextra = nextra({
  latex: false,
  search: {
    codeblocks: false,
  },
  defaultShowCopyCode: true,
});

export default withNextra({
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
});
