import { Link, useInRouterContext } from "react-router-dom";

export function InternalLink({ to, children, ...props }) {
    const hasRouter = useInRouterContext();
    return hasRouter
        ? <Link to={to} {...props}>{children}</Link>
        : <a href={to} {...props}>{children}</a>;
}

