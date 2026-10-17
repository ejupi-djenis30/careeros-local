import { lazy } from "react";
import { createBrowserRouter, createHashRouter, RouterProvider } from "react-router";
import { isDesktopShell } from "../platform/desktop";

const Workspace = lazy(() => import("./AuthenticatedWorkspace").then((module) => ({ default: module.AuthenticatedWorkspace })));
const createRouter = isDesktopShell() ? createHashRouter : createBrowserRouter;
const applicationRouter = createRouter([{ path: "*", element: <Workspace /> }]);

export function AuthenticatedRouter() {
    return <RouterProvider router={applicationRouter} />;
}
