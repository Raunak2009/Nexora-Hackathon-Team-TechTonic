import { Router, type IRouter } from "express";
import healthRouter from "./health";
import nexhireRouter from "./nexhire";

const router: IRouter = Router();

router.use(healthRouter);
router.use(nexhireRouter);

export default router;
