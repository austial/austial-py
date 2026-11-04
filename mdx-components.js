import { DocWrapper } from "@/components/doc-wrapper";
import * as elements from "@/components/mdx/elements";

export const useMDXComponents = (components) => ({
  ...elements,
  wrapper: DocWrapper,
  ...components,
});
