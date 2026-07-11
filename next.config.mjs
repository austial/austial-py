import nextra from "nextra";

const withNextra = nextra({
  latex: false,
  search: {
    codeblocks: false,
  },
});

export default withNextra({
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
});
